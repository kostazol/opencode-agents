#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parent
NON_LIVE_TESTS = frozenset({"test_fixture_validation.py", "test_harness.py", "test_runner.py", "test_workspace_guard.py"})
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
    logs = log_dir or Path(tempfile.mkdtemp(prefix="orchestrator-e2e-logs-"))
    logs.mkdir(parents=True, exist_ok=True)
    results = []
    for index, path in enumerate(tests):
        started = time.monotonic()
        stdout_path = logs / f".{path.stem}-{index}.stdout"
        stderr_path = logs / f".{path.stem}-{index}.stderr"
        timed_out = False
        with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open("w", encoding="utf-8") as stderr_file:
            process = subprocess.Popen([python, str(path)], stdout=stdout_file, stderr=stderr_file, text=True, start_new_session=True)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                _terminate_process_group(process)
                if process.poll() is None:
                    process.wait()
        duration = time.monotonic() - started
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        stdout_path.unlink()
        stderr_path.unlink()
        if timed_out:
            result = TestResult(path.name, "failed", duration, None, stdout, stderr, _failure_detail(stderr, stdout, f"timeout after {timeout}s"))
        else:
            status = "passed" if process.returncode == 0 else "failed"
            detail = "" if status == "passed" else _failure_detail(stderr, stdout, f"exit {process.returncode}")
            result = TestResult(path.name, status, duration, process.returncode, stdout, stderr, detail)
        result.log_path = logs / f"{path.stem}.log"
        result.log_path.write_text(f"STDOUT\n{result.stdout}\nSTDERR\n{result.stderr}", encoding="utf-8")
        results.append(result)
        if result.status == "failed" and fail_fast:
            results.extend(TestResult(remaining.name, "not-run", detail="fail-fast") for remaining in tests[index + 1:])
            break
    return results


def report(results: list[TestResult], aggregate_duration: float) -> None:
    for result in results:
        duration = f" {result.duration:.2f}s" if result.status in ("passed", "failed") else ""
        detail = f" — {result.detail}" if result.detail else ""
        log = f" [{result.log_path}]" if result.log_path is not None and result.status == "failed" else ""
        print(f"{result.status.upper():7} {result.name}{duration}{detail}{log}")
    counts = {status: sum(result.status == status for result in results) for status in ("passed", "failed", "skipped", "not-run")}
    print(f"TOTAL {aggregate_duration:.2f}s passed={counts['passed']} failed={counts['failed']} skipped={counts['skipped']} not-run={counts['not-run']}")


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run isolated live OpenCode E2E scripts sequentially.")
    parser.add_argument("--filter", dest="name_filter", help="Run tests whose filename contains this value.")
    parser.add_argument("--continue-on-failure", action="store_true", help="Run remaining tests after failure.")
    parser.add_argument("--timeout", type=float, help="Per-test process timeout in seconds.")
    parser.add_argument("--log-dir", type=Path, help="Directory for complete per-test stdout/stderr logs.")
    options = parser.parse_args(arguments)
    started = time.monotonic()
    try:
        discovered = discover_tests()
        selected, skipped = select_tests(discovered, options.name_filter)
        results = run_suite(selected, not options.continue_on_failure, options.timeout, options.log_dir)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    results.extend(skipped)
    report(results, time.monotonic() - started)
    return 1 if any(result.status == "failed" for result in results) else 0


def _failure_detail(stderr: str, stdout: str, fallback: str) -> str:
    lines = [line.strip() for line in (stderr or stdout).splitlines() if line.strip()]
    return lines[-1] if lines else fallback


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


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
