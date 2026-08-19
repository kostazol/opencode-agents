#!/usr/bin/env python3

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parent
EXIT_SUCCESS = 0
EXIT_TEST_FAILURE = 1
EXIT_RUNNER_ERROR = 2
EXIT_INTERRUPTED = 130
TELEMETRY_PATH_ENV = "ORCHESTRATOR_E2E_TELEMETRY_PATH"
DURATION_METRICS = ("fixture_setup", "environment_setup", "process_startup_to_health", "agent_inventory_loading", "prompt_to_question", "answer_to_idle", "prompt_to_idle", "subagent", "polling", "cleanup", "total")
COUNT_METRICS = ("serve_startups", "sessions", "primary_executions", "task_attempts", "task_successes", "task_failures", "task_incomplete")
TASK_AGENTS = frozenset({"orchestrator-discovery", "orchestrator-stage-planner", "orchestrator-stage-reviewer"})
NON_LIVE_TESTS = frozenset({"test_failure_catalog.py", "test_fixture_validation.py", "test_harness.py", "test_runner.py", "test_workflow_invariants.py", "test_workspace_guard.py"})
EXPECTED_LIVE_TESTS = (
    "test_approval.py",
    "test_complete.py",
    "test_discovery_questions.py",
    "test_first_stage.py",
    "test_human_review_creation.py",
    "test_human_review_gate.py",
    "test_human_review_mismatch_resume.py",
    "test_human_review_revise.py",
    "test_legacy_human_review_migration.py",
    "test_map_change_approval.py",
    "test_missing_scenario_expectation.py",
    "test_next_stage.py",
    "test_plan_approval.py",
    "test_plan_feedback.py",
    "test_plan_feedback_resume.py",
    "test_plan_revision.py",
    "test_question_answers.py",
    "test_reconcile_stage.py",
    "test_reset_stage_reserved_revision.py",
    "test_resume_review.py",
    "test_revise_stage.py",
    "test_revision_four.py",
    "test_revision_resume.py",
    "test_run_revise_continues.py",
)


@dataclass
class TestResult:
    name: str
    status: str
    duration: float = 0.0
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    detail: str = ""
    log_path: Path | None = None
    runner_error: bool = False
    telemetry: dict | None = None


class RunnerError(RuntimeError):
    pass


def discover_tests(directory: Path = ROOT, candidates: list[Path] | None = None, expected_names: tuple[str, ...] = EXPECTED_LIVE_TESTS) -> list[Path]:
    directory = directory.resolve()
    paths = candidates if candidates is not None else list(directory.glob("test_*.py"))
    discovered = []
    seen = set()
    for path in sorted(paths, key=lambda item: item.name):
        if path.name in NON_LIVE_TESTS:
            continue
        if path.is_symlink():
            raise ValueError(f"unsafe E2E discovery symlink: {path}")
        canonical = path.resolve()
        if directory not in canonical.parents or not canonical.is_file():
            raise ValueError(f"unsafe E2E discovery path: {path}")
        if canonical in seen:
            raise ValueError(f"duplicate E2E discovery: {path}")
        seen.add(canonical)
        discovered.append(canonical)
    actual_names = tuple(path.name for path in discovered)
    expected = tuple(sorted(expected_names))
    if actual_names != expected:
        missing = sorted(set(expected) - set(actual_names))
        unexpected = sorted(set(actual_names) - set(expected))
        raise ValueError(f"live E2E inventory mismatch: missing={missing}; unexpected={unexpected}")
    return discovered


def select_tests(tests: list[Path], name_filter: str | None) -> tuple[list[Path], list[TestResult]]:
    if name_filter is None:
        return tests, []
    selected = [path for path in tests if name_filter in path.stem or name_filter in path.name]
    if not selected:
        raise ValueError(f"E2E filter matched no tests: {name_filter}")
    skipped = [TestResult(path.name, "skipped", detail=f"filtered by {name_filter!r}") for path in tests if path not in selected]
    return selected, skipped


def run_suite(tests: list[Path], fail_fast: bool = True, timeout: float | None = None, log_dir: Path | None = None, python: str = sys.executable) -> list[TestResult]:
    try:
        logs = log_dir or Path(tempfile.mkdtemp(prefix="orchestrator-e2e-logs-"))
        logs.mkdir(parents=True, exist_ok=True)
    except Exception as error:
        raise RunnerError(_exception_detail("cannot prepare log directory", error)) from error
    results = []
    for index, path in enumerate(tests):
        started = time.monotonic()
        stdout_path = logs / f".{path.stem}-{index}.stdout"
        stderr_path = logs / f".{path.stem}-{index}.stderr"
        log_path = logs / f"{path.stem}.log"
        telemetry_path = logs / f".{path.stem}-{index}-{uuid.uuid4().hex}.telemetry.json"
        stdout_file = None
        stderr_file = None
        process = None
        timed_out = False
        interrupted = False
        failures = []
        try:
            log_path.unlink(missing_ok=True)
            telemetry_path.unlink(missing_ok=True)
        except Exception as error:
            failures.append(_exception_detail("stale failure log cleanup failure", error))
        try:
            stdout_file = stdout_path.open("w", encoding="utf-8")
            stderr_file = stderr_path.open("w", encoding="utf-8")
        except KeyboardInterrupt:
            interrupted = True
            failures.append("interrupted by KeyboardInterrupt during output setup")
        except Exception as error:
            failures.append(_exception_detail("output setup failure", error))
        if not failures:
            try:
                child_environment = os.environ.copy()
                child_environment.pop("PYTHONOPTIMIZE", None)
                child_environment[TELEMETRY_PATH_ENV] = str(telemetry_path)
                process = subprocess.Popen([python, str(path)], stdout=stdout_file, stderr=stderr_file, text=True, start_new_session=True, env=child_environment)
            except KeyboardInterrupt:
                interrupted = True
                failures.append("interrupted by KeyboardInterrupt during process spawn")
            except Exception as error:
                failures.append(_exception_detail("process spawn failure", error))
        if process is not None:
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
            except KeyboardInterrupt:
                interrupted = True
                failures.append("interrupted by KeyboardInterrupt")
            except Exception as error:
                failures.append(_exception_detail("process wait failure", error))
            finally:
                try:
                    _terminate_process_group(process)
                except Exception as error:
                    failures.append(_exception_detail("process-group cleanup failure", error))
                if process.poll() is None:
                    try:
                        process.wait(timeout=1)
                    except Exception as error:
                        failures.append(_exception_detail("process reap failure", error))
                        try:
                            process.kill()
                            process.wait(timeout=1)
                        except Exception as kill_error:
                            failures.append(_exception_detail("process fallback cleanup failure", kill_error))
        for stream_name, stream in (("stdout", stdout_file), ("stderr", stderr_file)):
            if stream is not None:
                try:
                    stream.close()
                except Exception as error:
                    failures.append(_exception_detail(f"{stream_name} close failure", error))
        duration = time.monotonic() - started
        stdout, stdout_error = _read_output(stdout_path, "stdout")
        stderr, stderr_error = _read_output(stderr_path, "stderr")
        failures.extend(error for error in (stdout_error, stderr_error) if error)
        for output_path in (stdout_path, stderr_path):
            try:
                output_path.unlink(missing_ok=True)
            except Exception as error:
                failures.append(_exception_detail("temporary output cleanup failure", error))
        returncode = process.returncode if process is not None else None
        telemetry, telemetry_error = _read_telemetry(telemetry_path, returncode == 0 and not timed_out and not interrupted)
        try:
            telemetry_path.unlink(missing_ok=True)
        except Exception as error:
            failures.append(_exception_detail("temporary telemetry cleanup failure", error))
        if telemetry_error:
            failures.append(telemetry_error)
        child_detail = ""
        if timed_out:
            child_detail = f"timeout after {timeout}s"
        elif returncode not in (None, 0):
            child_detail = _failure_detail(stderr, stdout, f"exit {returncode}")
        detail = _combine_details(child_detail, failures)
        status = "interrupted" if interrupted else "failed" if detail or timed_out or returncode != 0 else "passed"
        result = TestResult(path.name, status, duration, returncode, stdout, stderr, detail, runner_error=bool(failures), telemetry=telemetry)
        try:
            log_path.write_text(f"DETAIL\n{result.detail}\nSTDOUT\n{result.stdout}\nSTDERR\n{result.stderr}", encoding="utf-8")
            result.log_path = log_path
        except Exception as error:
            result.detail = _combine_details(result.detail, [_exception_detail("failure log write failure", error)])
            result.runner_error = True
            if result.status == "passed":
                result.status = "failed"
        results.append(result)
        if result.status == "interrupted":
            results.extend(TestResult(remaining.name, "not-run", detail="interrupted") for remaining in tests[index + 1:])
            break
        if result.status == "failed" and fail_fast:
            results.extend(TestResult(remaining.name, "not-run", detail="fail-fast") for remaining in tests[index + 1:])
            break
    return results


def _read_telemetry(path: Path, require_complete: bool = False) -> tuple[dict | None, str]:
    try:
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
    except FileNotFoundError:
        return None, "telemetry failure: missing telemetry fixture"
    except Exception as error:
        return None, _exception_detail("telemetry failure: malformed telemetry fixture", error)
    try:
        _validate_telemetry(payload, require_complete)
    except Exception as error:
        return None, _exception_detail("telemetry failure: invalid telemetry fixture", error)
    return payload, ""


def _validate_telemetry(payload: object, require_complete: bool = False) -> None:
    if not isinstance(payload, dict):
        raise ValueError("root must be an object")
    if set(payload) != {"schema_version", "status", "durations_seconds", "counts", "ordered_agents"}:
        raise ValueError("unexpected root fields")
    if payload["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    if payload["status"] not in ("complete", "partial"):
        raise ValueError("status must be complete or partial")
    if require_complete and payload["status"] != "complete":
        raise ValueError("passed child requires complete telemetry")
    durations = payload["durations_seconds"]
    if not isinstance(durations, dict) or set(durations) != set(DURATION_METRICS):
        raise ValueError("duration metrics mismatch")
    for name in DURATION_METRICS:
        metric = durations[name]
        if not isinstance(metric, dict) or set(metric) != {"values", "unavailable"}:
            raise ValueError(f"invalid duration metric {name}")
        values = metric["values"]
        unavailable = metric["unavailable"]
        if not isinstance(values, list) or any(not _is_duration(value) for value in values):
            raise ValueError(f"invalid duration values for {name}")
        if not _is_count(unavailable):
            raise ValueError(f"invalid unavailable count for {name}")
    counts = payload["counts"]
    if not isinstance(counts, dict) or set(counts) != set(COUNT_METRICS) or any(not _is_count(counts[name]) for name in COUNT_METRICS):
        raise ValueError("count metrics mismatch")
    if counts["task_attempts"] != counts["task_successes"] + counts["task_failures"] + counts["task_incomplete"]:
        raise ValueError("task classifications do not sum to attempts")
    agents = payload["ordered_agents"]
    if not isinstance(agents, list) or any(not isinstance(agent, str) or agent not in TASK_AGENTS for agent in agents):
        raise ValueError("ordered_agents contains invalid agent")
    if len(agents) != counts["task_successes"]:
        raise ValueError("ordered_agents count does not match task_successes")
    subagents = durations["subagent"]
    if len(subagents["values"]) + subagents["unavailable"] != counts["task_attempts"]:
        raise ValueError("subagent durations do not account for every task attempt")
    if counts["sessions"] > 0 and counts["serve_startups"] == 0:
        raise ValueError("sessions require a serve startup")
    if counts["primary_executions"] > 0 and counts["sessions"] == 0:
        raise ValueError("primary executions require a session")
    if payload["status"] == "complete" and counts["sessions"] > counts["primary_executions"]:
        raise ValueError("complete telemetry requires at least one primary execution per session")
    if payload["status"] == "complete":
        if counts["sessions"] == 0 or counts["primary_executions"] < counts["sessions"]:
            raise ValueError("complete telemetry requires at least one primary execution per session")
        initial_prompts = len(durations["prompt_to_question"]["values"]) + len(durations["prompt_to_idle"]["values"])
        if initial_prompts != counts["sessions"]:
            raise ValueError("complete telemetry requires one initial prompt duration per session")
        if len(durations["answer_to_idle"]["values"]) != counts["primary_executions"] - counts["sessions"]:
            raise ValueError("complete telemetry answer continuations do not match primary executions")
        if len(durations["prompt_to_question"]["values"]) != len(durations["answer_to_idle"]["values"]):
            raise ValueError("complete telemetry questions do not match answer continuations")
        for name in ("prompt_to_question", "answer_to_idle", "prompt_to_idle", "polling"):
            if durations[name]["unavailable"] != 0:
                raise ValueError(f"complete telemetry cannot have unavailable {name} durations")
        if len(durations["polling"]["values"]) != counts["primary_executions"] or durations["polling"]["unavailable"] != 0:
            raise ValueError("complete telemetry requires one polling duration per primary execution")
        if counts["serve_startups"] == 0:
            raise ValueError("complete telemetry requires at least one serve startup")
        for name in ("fixture_setup", "environment_setup", "process_startup_to_health", "agent_inventory_loading", "cleanup", "total"):
            metric = durations[name]
            if len(metric["values"]) != counts["serve_startups"] or metric["unavailable"] != 0:
                raise ValueError(f"complete telemetry requires one available {name} duration per serve startup")


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_duration(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _duration_summary(values: list[float], unavailable: int = 0) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "unavailable": unavailable, "sum": 0.0, "median": None, "p95": None}
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    return {"count": len(ordered), "unavailable": unavailable, "sum": sum(ordered), "median": statistics.median(ordered), "p95": p95}


def aggregate_telemetry(results: list[TestResult], total_wall_seconds: float) -> dict:
    statuses = {status: sum(result.status == status for result in results) for status in ("passed", "failed", "interrupted", "skipped", "not-run")}
    valid = [result.telemetry for result in results if result.telemetry is not None]
    counts = {name: sum(telemetry["counts"][name] for telemetry in valid) for name in COUNT_METRICS}
    durations = {}
    for name in DURATION_METRICS:
        values = [value for telemetry in valid for value in telemetry["durations_seconds"][name]["values"]]
        unavailable = sum(telemetry["durations_seconds"][name]["unavailable"] for telemetry in valid)
        durations[name] = _duration_summary(values, unavailable)
    return {
        "schema_version": 1,
        "total_wall_seconds": total_wall_seconds,
        "tests": {"count": len(results), "statuses": statuses, "telemetry_available": len(valid), "telemetry_unavailable": len(results) - len(valid)},
        "counts": counts,
        "durations_seconds": durations,
        "ordered_agents": [agent for telemetry in valid for agent in telemetry["ordered_agents"]],
    }


def _atomic_write_json(path: Path, payload: dict) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def report(results: list[TestResult], aggregate_duration: float) -> None:
    for result in results:
        duration = f" {result.duration:.2f}s" if result.status in ("passed", "failed", "interrupted") else ""
        detail = f" — {result.detail}" if result.detail else ""
        log = f" [{result.log_path}]" if result.log_path is not None and result.status in ("failed", "interrupted") else ""
        print(f"{result.status.upper():7} {result.name}{duration}{detail}{log}")
    counts = {status: sum(result.status == status for result in results) for status in ("passed", "failed", "interrupted", "skipped", "not-run")}
    print(f"TOTAL {aggregate_duration:.2f}s passed={counts['passed']} failed={counts['failed']} interrupted={counts['interrupted']} skipped={counts['skipped']} not-run={counts['not-run']}")
    aggregate = aggregate_telemetry(results, aggregate_duration)
    metric_counts = " ".join(f"{name}={aggregate['counts'][name]}" for name in COUNT_METRICS)
    print(f"COUNTS {metric_counts}")
    for name in DURATION_METRICS:
        metric = aggregate["durations_seconds"][name]
        median = "unavailable" if metric["median"] is None else f"{metric['median']:.3f}"
        p95 = "unavailable" if metric["p95"] is None else f"{metric['p95']:.3f}"
        print(f"DURATION {name} count={metric['count']} unavailable={metric['unavailable']} sum={metric['sum']:.3f} median={median} p95={p95}")
    print(f"AGENTS {json.dumps(aggregate['ordered_agents'], ensure_ascii=False)}")


def main(arguments: list[str] | None = None) -> int:
    with _termination_as_interrupt():
        return _main(arguments)


def _main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run isolated live OpenCode E2E scripts sequentially.", epilog=f"Exit codes: {EXIT_SUCCESS}=success, {EXIT_TEST_FAILURE}=test failure, {EXIT_RUNNER_ERROR}=runner error, {EXIT_INTERRUPTED}=interrupted.")
    parser.add_argument("--filter", dest="name_filter", help="Run tests whose filename contains this value.")
    parser.add_argument("--continue-on-failure", action="store_true", help="Run remaining tests after failure.")
    parser.add_argument("--timeout", type=float, help="Per-test process timeout in seconds.")
    parser.add_argument("--log-dir", type=Path, help="Directory for complete per-test stdout/stderr logs.")
    parser.add_argument("--json-report", type=Path, help="Atomically write machine-readable aggregate telemetry to PATH.")
    options = parser.parse_args(arguments)
    if options.json_report is not None:
        try:
            options.json_report = _external_report_path(options.json_report)
        except ValueError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return EXIT_RUNNER_ERROR
    started = time.monotonic()
    results = []
    skipped = []
    try:
        discovered = discover_tests()
        selected, skipped = select_tests(discovered, options.name_filter)
        results = run_suite(selected, not options.continue_on_failure, options.timeout, options.log_dir)
    except KeyboardInterrupt:
        print("ERROR: interrupted by KeyboardInterrupt", file=sys.stderr)
        if results:
            report(results, time.monotonic() - started)
        return EXIT_INTERRUPTED
    except Exception as error:
        print(f"ERROR: {_exception_detail('runner failure', error)}", file=sys.stderr)
        if results:
            report(results, time.monotonic() - started)
        return EXIT_RUNNER_ERROR
    results.extend(skipped)
    aggregate_duration = time.monotonic() - started
    if results:
        report(results, aggregate_duration)
    if options.json_report is not None:
        try:
            _atomic_write_json(options.json_report, aggregate_telemetry(results, aggregate_duration))
        except Exception as error:
            print(f"ERROR: {_exception_detail('JSON report failure', error)}", file=sys.stderr)
            return EXIT_RUNNER_ERROR
    if any(result.status == "interrupted" for result in results):
        return EXIT_INTERRUPTED
    if any(result.runner_error for result in results):
        return EXIT_RUNNER_ERROR
    return EXIT_TEST_FAILURE if any(result.status == "failed" for result in results) else EXIT_SUCCESS


@contextmanager
def _termination_as_interrupt():
    signals = [signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        signals.append(signal.SIGHUP)
    previous = {termination_signal: signal.getsignal(termination_signal) for termination_signal in signals}
    def interrupt(_signal_number, _frame):
        raise KeyboardInterrupt
    try:
        for termination_signal in signals:
            signal.signal(termination_signal, interrupt)
        yield
    finally:
        for termination_signal, handler in previous.items():
            signal.signal(termination_signal, handler)


def _external_report_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repository = ROOT.parents[1]
    if resolved == repository or repository in resolved.parents:
        raise ValueError(f"JSON report path must be outside repository: {path}")
    return resolved


def _failure_detail(stderr: str, stdout: str, fallback: str) -> str:
    lines = [line.strip() for line in (stderr or stdout).splitlines() if line.strip()]
    return lines[-1] if lines else fallback


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


def _read_output(path: Path, stream_name: str) -> tuple[str, str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace"), ""
    except Exception as error:
        return "", _exception_detail(f"{stream_name} read failure", error)


def _exception_detail(context: str, error: BaseException) -> str:
    return f"{context}: {type(error).__name__}: {error}"


def _combine_details(primary: str, additional: list[str]) -> str:
    parts = [primary] if primary else []
    parts.extend(detail for detail in additional if detail)
    return "; ".join(parts)


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.01)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
