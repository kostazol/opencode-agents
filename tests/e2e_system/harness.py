from __future__ import annotations

import json
import hashlib
import itertools
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = int(os.environ.get("ORCHESTRATOR_E2E_TIMEOUT_SECONDS", "300"))
TASK_AGENTS = frozenset({"orchestrator-discovery", "orchestrator-stage-planner", "orchestrator-stage-reviewer"})
_TELEMETRY_CONTRIBUTIONS: dict[Path, dict[int, dict[str, Any]]] = {}
_TELEMETRY_WORKSPACE_IDS = itertools.count()
TELEMETRY_PATH_ENV = "ORCHESTRATOR_E2E_TELEMETRY_PATH"
DURATION_METRICS = ("fixture_setup", "environment_setup", "process_startup_to_health", "agent_inventory_loading", "prompt_to_question", "answer_to_idle", "prompt_to_idle", "subagent", "polling", "cleanup", "total")
COUNT_METRICS = ("serve_startups", "sessions", "primary_executions", "task_attempts", "task_successes", "task_failures", "task_incomplete")


@dataclass(frozen=True)
class TaskCall:
    agent_name: str | None
    call_id: str | None
    order: int
    input: dict[str, Any] | None
    status: str
    execution_completed: bool
    started_at_ms: int | None
    ended_at_ms: int | None
    raw_output: Any
    execution_error: str | None
    compact_result: str | None
    result_valid: bool
    parse_diagnostic: str | None

    @property
    def successful(self) -> bool:
        return self.agent_name in TASK_AGENTS and self.execution_completed and self.execution_error is None and self.result_valid

    @property
    def failed(self) -> bool:
        return self.status == "error" or self.execution_error is not None

    @property
    def incomplete(self) -> bool:
        return not self.successful and not self.failed

    @property
    def output(self) -> Any:
        return self.raw_output

    @property
    def error(self) -> str | None:
        return self.execution_error

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at_ms is None or self.ended_at_ms is None or self.ended_at_ms < self.started_at_ms:
            return None
        return (self.ended_at_ms - self.started_at_ms) / 1000


@dataclass(frozen=True)
class WorkspaceEntry:
    kind: str
    digest_or_target: str | None
    mode: int
    mtime_ns: int


@dataclass(frozen=True)
class WorkspaceSnapshot:
    root: Path
    allowed_target: Path
    entries: dict[Path, WorkspaceEntry]
    workflow_targets: frozenset[Path]
    runtime_roots: frozenset[Path]
    git_status: str


def capture_workspace_snapshot(root: Path, allowed_target: Path) -> WorkspaceSnapshot:
    root = root.resolve()
    if allowed_target.is_absolute():
        raise AssertionError(f"allowed request target must be relative: {allowed_target}")
    canonical_target = Path(os.path.normpath(str(allowed_target)))
    if canonical_target.parts[:1] != ("1_orchestrator",) or len(canonical_target.parts) != 2 or canonical_target.parts[1] in ("", ".", ".."):
        raise AssertionError(f"allowed request target must be exact 1_orchestrator/<request>: {allowed_target}")
    entries = {}
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        directory_names[:] = sorted(name for name in directory_names if (directory_path / name).relative_to(root).parts[:2] != (".opencode", "node_modules"))
        for name in sorted(directory_names + file_names):
            path = directory_path / name
            relative = path.relative_to(root)
            if relative in (Path(".opencode/package.json"), Path(".opencode/package-lock.json")):
                continue
            metadata = path.lstat()
            mode = stat.S_IMODE(metadata.st_mode)
            if stat.S_ISLNK(metadata.st_mode):
                if relative in canonical_target.parents:
                    raise AssertionError(f"allowed request target has symlink ancestor: {relative} -> {os.readlink(path)}")
                if relative == canonical_target or canonical_target in relative.parents:
                    resolved = path.resolve(strict=False)
                    resolved_target = root / canonical_target
                    if resolved != resolved_target and resolved_target not in resolved.parents:
                        raise AssertionError(f"allowed request target contains escaping symlink: {relative} -> {os.readlink(path)}")
                entries[relative] = WorkspaceEntry("symlink", os.readlink(path), mode, metadata.st_mtime_ns)
            elif stat.S_ISDIR(metadata.st_mode):
                entries[relative] = WorkspaceEntry("directory", None, mode, metadata.st_mtime_ns)
            elif stat.S_ISREG(metadata.st_mode):
                entries[relative] = WorkspaceEntry("file", hashlib.sha256(path.read_bytes()).hexdigest(), mode, metadata.st_mtime_ns)
            else:
                entries[relative] = WorkspaceEntry("other", None, mode, metadata.st_mtime_ns)
    orchestrator = root / "1_orchestrator"
    workflow_targets = frozenset(path.relative_to(root) for path in orchestrator.iterdir() if path.is_dir()) if orchestrator.is_dir() else frozenset()
    runtime_roots = frozenset(path for path in (Path(".opencode/node_modules"), Path(".opencode/package.json"), Path(".opencode/package-lock.json")) if (root / path).exists() or (root / path).is_symlink())
    return WorkspaceSnapshot(root, canonical_target, entries, workflow_targets, runtime_roots, _git_status(root, canonical_target))


def assert_workspace_unchanged(before: WorkspaceSnapshot, after: WorkspaceSnapshot) -> None:
    if before.root != after.root or before.allowed_target != after.allowed_target:
        raise AssertionError(f"workspace snapshot identity mismatch: before={before}; after={after}")
    changed = []
    for path in sorted(before.entries.keys() | after.entries.keys()):
        if before.entries.get(path) == after.entries.get(path):
            continue
        if _is_allowed_workspace_change(path, before.entries.get(path), after.entries.get(path), before.allowed_target, before.entries, after.entries, before.runtime_roots != after.runtime_roots):
            continue
        changed.append(f"{path}: {before.entries.get(path)!r} -> {after.entries.get(path)!r}")
    unexpected_targets = sorted(target for target in after.workflow_targets - before.workflow_targets if target != before.allowed_target)
    if unexpected_targets:
        changed.append(f"unexpected workflow targets: {unexpected_targets!r}")
    if before.git_status != after.git_status:
        changed.append(f"git status changed: {before.git_status!r} -> {after.git_status!r}")
    if changed:
        raise AssertionError("product workspace mutation detected:\n" + "\n".join(changed))


def _is_allowed_workspace_change(path: Path, before: WorkspaceEntry | None, after: WorkspaceEntry | None, allowed_target: Path, before_entries: dict[Path, WorkspaceEntry], after_entries: dict[Path, WorkspaceEntry], runtime_roots_changed: bool) -> bool:
    if path == allowed_target or allowed_target in path.parents:
        return True
    if path in allowed_target.parents and before is None and after is not None and after.kind == "directory":
        return True
    if path in allowed_target.parents and allowed_target not in before_entries and allowed_target in after_entries and before is not None and after is not None and before.kind == after.kind == "directory" and before.mode == after.mode and before.digest_or_target == after.digest_or_target:
        return True
    if runtime_roots_changed and path == Path(".opencode") and before is not None and after is not None and before.kind == after.kind == "directory" and before.mode == after.mode and before.digest_or_target == after.digest_or_target:
        return True
    return False


def _git_status(root: Path, allowed_target: Path) -> str:
    command = ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", ".", f":(exclude){allowed_target}", f":(exclude){allowed_target}/**", ":(exclude).opencode/node_modules", ":(exclude).opencode/node_modules/**", ":(exclude).opencode/package.json", ":(exclude).opencode/package-lock.json"]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if result.returncode == 128 and "not a git repository" in result.stderr:
        return "not-a-worktree"
    if result.returncode != 0:
        raise AssertionError(f"cannot capture workspace git status: exit={result.returncode}; stderr={result.stderr.strip()}")
    return result.stdout


_TASK_WRAPPER = re.compile(r'<task id="[^"\r\n]+" state="completed">\n<task_result>\n(?P<result>.*?)\n</task_result>\n</task>', re.DOTALL)
def _compact_task_result(agent_name: str | None, output: Any) -> tuple[str | None, bool, str | None]:
    if not isinstance(output, str):
        return None, False, "task output is not a string"
    wrapped = _TASK_WRAPPER.fullmatch(output)
    if wrapped is None:
        return None, False, "malformed task result wrapper"
    compact_result = wrapped.group("result")
    if agent_name == "orchestrator-discovery":
        labels = ("DISCOVERY", "ARTIFACT", "QUESTIONS", "PLAN", "SUMMARY")
        statuses = {"QUESTIONS", "READY_FOR_APPROVAL", "BLOCKED"}
    elif agent_name == "orchestrator-stage-planner":
        labels = ("STAGE_PLAN", "STAGE", "REVISION", "ARTIFACT", "SUMMARY")
        statuses = {"REVIEW", "MAP_CHANGE_REQUIRED", "BLOCKED"}
    elif agent_name == "orchestrator-stage-reviewer":
        labels = ("STAGE_REVIEW", "STAGE", "REVISION", "REVIEW", "FINDINGS", "SUMMARY")
        statuses = {"PASS", "REVISE", "MAP_CHANGE_REQUIRED", "BLOCKED"}
    else:
        return compact_result, False, f"unknown task agent: {agent_name!r}"
    lines = compact_result.splitlines()
    if len(lines) != len(labels):
        return compact_result, False, f"expected {len(labels)} compact result lines, got {len(lines)}"
    values = {}
    for line, label in zip(lines, labels):
        prefix = f"{label}: "
        if not line.startswith(prefix):
            return compact_result, False, f"expected label {label!r}"
        values[label] = line[len(prefix):]
    status = values[labels[0]]
    if status not in statuses:
        return compact_result, False, f"invalid {labels[0]} status: {status!r}"
    summary = values["SUMMARY"]
    if not summary or summary.strip() != summary:
        return compact_result, False, "SUMMARY must be nonempty and trimmed"
    if agent_name == "orchestrator-discovery":
        for label in ("ARTIFACT", "QUESTIONS", "PLAN"):
            if not values[label] or values[label].strip() != values[label]:
                return compact_result, False, f"{label} must be nonempty and trimmed"
        if not _workflow_artifact_path(values["ARTIFACT"], "discovery"):
            return compact_result, False, f"invalid ARTIFACT path: {values['ARTIFACT']!r}"
        if values["QUESTIONS"] != "none" and not _workflow_artifact_path(values["QUESTIONS"], "questions"):
            return compact_result, False, f"invalid QUESTIONS path: {values['QUESTIONS']!r}"
        if not _workflow_artifact_path(values["PLAN"], "plan"):
            return compact_result, False, f"invalid PLAN path: {values['PLAN']!r}"
        request_roots = {_workflow_request_root(values[label]) for label in ("ARTIFACT", "PLAN")}
        if values["QUESTIONS"] != "none":
            request_roots.add(_workflow_request_root(values["QUESTIONS"]))
        if len(request_roots) != 1:
            return compact_result, False, f"discovery paths use different request roots: {sorted(request_roots)!r}"
        return compact_result, True, None
    stage = values["STAGE"]
    if re.fullmatch(r"S[0-9]{2}", stage) is None:
        return compact_result, False, f"invalid STAGE: {stage!r}"
    if re.fullmatch(r"[1-9][0-9]*", values["REVISION"]) is None:
        return compact_result, False, f"invalid REVISION: {values['REVISION']!r}"
    if agent_name == "orchestrator-stage-planner":
        artifact = values["ARTIFACT"]
        if not artifact or artifact.strip() != artifact:
            return compact_result, False, "ARTIFACT must be nonempty and trimmed"
        if artifact != "none" and not _workflow_artifact_path(artifact, "stage"):
            return compact_result, False, f"invalid ARTIFACT path: {artifact!r}"
        if artifact != "none" and re.fullmatch(rf"{re.escape(stage[1:])}-[^/\s]+\.md", Path(artifact).name) is None:
            return compact_result, False, f"ARTIFACT path does not match STAGE: {artifact!r}"
        return compact_result, True, None
    review = values["REVIEW"]
    if not review or review.strip() != review:
        return compact_result, False, "REVIEW must be nonempty and trimmed"
    if not _workflow_artifact_path(review, "review"):
        return compact_result, False, f"invalid REVIEW path: {review!r}"
    if re.fullmatch(rf"{re.escape(stage[1:])}(?:-human-review)?\.md", Path(review).name) is None:
        return compact_result, False, f"REVIEW path does not match STAGE: {review!r}"
    if re.fullmatch(r"0|[1-9][0-9]*", values["FINDINGS"]) is None:
        return compact_result, False, f"invalid FINDINGS: {values['FINDINGS']!r}"
    findings = int(values["FINDINGS"])
    if status == "PASS" and findings != 0:
        return compact_result, False, "PASS requires zero FINDINGS"
    if status == "REVISE" and findings == 0:
        return compact_result, False, "REVISE requires positive FINDINGS"
    return compact_result, True, None


def _workflow_artifact_path(value: str, kind: str) -> bool:
    request_root = r"1_orchestrator/(?!\.{1,2}/)[^/\s]+"
    patterns = {
        "discovery": rf"{request_root}/discovery\.md",
        "questions": rf"{request_root}/questions\.md",
        "plan": rf"{request_root}/plan\.md",
        "stage": rf"{request_root}/stages/[^/\s]+\.md",
        "review": rf"{request_root}/reviews/[^/\s]+\.md",
    }
    return re.fullmatch(patterns[kind], value) is not None


def _workflow_request_root(value: str) -> str:
    return "/".join(value.split("/", 2)[:2])


def task_trace(messages: list[dict[str, Any]]) -> list[TaskCall]:
    result = []
    for message in messages:
        for part in message.get("parts", []):
            if not isinstance(part, dict) or part.get("type") != "tool" or part.get("tool") != "task":
                continue
            state = part.get("state")
            task_input = state.get("input") if isinstance(state, dict) else None
            raw_output = state.get("output") if isinstance(state, dict) else None
            raw_error = state.get("error") if isinstance(state, dict) else None
            error = raw_error if isinstance(raw_error, str) else repr(raw_error) if raw_error is not None else None
            status = state.get("status") if isinstance(state, dict) else None
            raw_task_time = state.get("time") if isinstance(state, dict) else None
            task_time: dict[str, Any] = raw_task_time if isinstance(raw_task_time, dict) else {}
            agent_name = task_input.get("subagent_type") if isinstance(task_input, dict) and isinstance(task_input.get("subagent_type"), str) else None
            compact_result, result_valid, parse_diagnostic = _compact_task_result(agent_name, raw_output)
            result.append(TaskCall(
                agent_name=agent_name,
                call_id=part.get("callID") if isinstance(part.get("callID"), str) else None,
                order=len(result),
                input=task_input if isinstance(task_input, dict) else None,
                status=status if isinstance(status, str) else "unknown",
                execution_completed=status == "completed",
                started_at_ms=_integer_milliseconds(task_time.get("start")),
                ended_at_ms=_integer_milliseconds(task_time.get("end")),
                raw_output=raw_output,
                execution_error=error,
                compact_result=compact_result,
                result_valid=result_valid,
                parse_diagnostic=parse_diagnostic,
            ))
    return result


def _integer_milliseconds(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 2**53 else None


def successful_task_calls(messages: list[dict[str, Any]]) -> list[TaskCall]:
    return [call for call in task_trace(messages) if call.successful]


def failed_task_calls(messages: list[dict[str, Any]]) -> list[TaskCall]:
    return [call for call in task_trace(messages) if call.failed]


def incomplete_task_calls(messages: list[dict[str, Any]]) -> list[TaskCall]:
    return [call for call in task_trace(messages) if call.incomplete]


def assert_task_sequence(messages: list[dict[str, Any]], expected_agents: list[str]) -> list[TaskCall]:
    attempts = task_trace(messages)
    successful = [call for call in attempts if call.successful]
    actual_agents = [call.agent_name for call in successful]
    invalid = [call for call in attempts if not call.successful]
    if len(attempts) != len(expected_agents) or actual_agents != expected_agents or invalid:
        raise AssertionError(f"task trace mismatch: expected={expected_agents!r}; attempts={attempts!r}; successful={successful!r}; failed_or_incomplete={invalid!r}")
    return successful


def _assistant_message_boundary(messages: list[dict[str, Any]]) -> dict[str, bool]:
    return {message["info"]["id"]: isinstance(message["info"].get("time"), dict) and message["info"]["time"].get("completed") is not None for message in messages if isinstance(message, dict) and isinstance(message.get("info"), dict) and message["info"].get("role") == "assistant" and isinstance(message["info"].get("id"), str)}


def _new_assistant_turn_state(messages: list[dict[str, Any]], baseline: dict[str, bool] | frozenset[str]) -> tuple[bool, str]:
    assistants = [message for message in messages if isinstance(message, dict) and isinstance(message.get("info"), dict) and message["info"].get("role") == "assistant"]
    baseline_states = {message_id: True for message_id in baseline} if isinstance(baseline, frozenset) else baseline
    new_assistants = [message for message in assistants if isinstance(message["info"].get("id"), str) and (message["info"]["id"] not in baseline_states or not baseline_states[message["info"]["id"]])]
    if not new_assistants:
        ids = [message["info"].get("id") for message in assistants]
        return False, f"no new assistant turn; assistant_ids={ids!r}"
    turn = new_assistants[-1]
    info = turn["info"]
    completed = isinstance(info.get("time"), dict) and info["time"].get("completed") is not None
    calls = task_trace([turn])
    tasks_terminal = all(call.status in ("completed", "error") for call in calls)
    diagnostic = f"assistant_id={info.get('id')!r}; completed={completed}; tasks={calls!r}"
    return completed and tasks_terminal, diagnostic


def _decode_sse_data(lines: list[str]) -> dict[str, Any] | None:
    data = "\n".join(line[5:].lstrip(" ") for line in lines if line.startswith("data:"))
    if not data:
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _session_event_kind(payload: dict[str, Any], session_id: str) -> str | None:
    event_type = payload.get("type")
    if event_type == "server.connected":
        return "connected"
    properties = payload.get("properties")
    if not isinstance(properties, dict) or properties.get("sessionID") != session_id:
        return None
    if event_type == "session.idle":
        return "idle"
    status = properties.get("status")
    if event_type == "session.status" and isinstance(status, dict) and status.get("type") == "idle":
        return "idle"
    return None


class SessionEventWatcher:
    def __init__(self, base_url: str, session_id: str):
        self.base_url = base_url
        self.session_id = session_id
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._condition = threading.Condition()
        self._idle_count = 0
        self._connected = False
        self._error: BaseException | None = None
        self._response: Any = None
        self._thread = threading.Thread(target=self._run, name=f"opencode-events-{session_id}", daemon=True)

    def __enter__(self):
        self._thread.start()
        if not self._ready.wait(TIMEOUT_SECONDS):
            failure = AssertionError("event stream did not emit server.connected before deadline")
            self._close_preserving(failure)
            raise failure
        if not self._connected or self._error is not None:
            error = self._error
            failure = AssertionError(f"event stream failed before readiness: {error!r}")
            self._close_preserving(failure)
            raise failure from error
        return self

    def __exit__(self, exception_type, exception, _traceback):
        try:
            self.close()
        except BaseException as cleanup_error:
            if exception is None:
                raise
            exception.add_note(f"event watcher cleanup failed: {cleanup_error}")
        return False

    def boundary(self) -> int:
        with self._condition:
            return self._idle_count

    def has_idle_after(self, boundary: int) -> bool:
        with self._condition:
            return self._idle_count > boundary

    def wait_for_event(self, timeout: float) -> None:
        with self._condition:
            self._condition.wait(timeout)

    def diagnostic(self, boundary: int) -> str:
        with self._condition:
            return f"event_idle_count={self._idle_count}; event_boundary={boundary}; event_error={self._error!r}"

    def close(self) -> None:
        self._stopped.set()
        response = self._response
        close_error = None
        try:
            if response is not None:
                raw = getattr(getattr(response, "fp", None), "raw", None)
                response_socket = getattr(raw, "_sock", None)
                if response_socket is not None:
                    try:
                        response_socket.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                response.close()
        except BaseException as error:
            close_error = error
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            failure = AssertionError("event watcher did not stop")
            if close_error is not None:
                failure.add_note(f"event response cleanup failed: {close_error}")
            raise failure
        if close_error is not None:
            raise close_error

    def _close_preserving(self, failure: BaseException) -> None:
        try:
            self.close()
        except BaseException as cleanup_error:
            failure.add_note(f"event watcher cleanup failed: {cleanup_error}")

    def _run(self) -> None:
        event_lines = []
        try:
            request = Request(f"{self.base_url}/event", method="GET", headers={"Accept": "text/event-stream"})
            self._response = urlopen(request, timeout=TIMEOUT_SECONDS)
            for raw_line in self._response:
                if self._stopped.is_set():
                    break
                line = raw_line.decode(errors="replace").rstrip("\r\n")
                if line:
                    event_lines.append(line)
                    continue
                self._consume_event(event_lines)
                event_lines = []
            if event_lines:
                self._consume_event(event_lines)
        except BaseException as error:
            if not self._stopped.is_set():
                self._error = error
        finally:
            self._ready.set()
            with self._condition:
                self._condition.notify_all()

    def _consume_event(self, lines: list[str]) -> None:
        payload = _decode_sse_data(lines)
        kind = _session_event_kind(payload, self.session_id) if payload is not None else None
        if kind == "connected":
            self._connected = True
            self._ready.set()
        elif kind == "idle":
            with self._condition:
                self._idle_count += 1
                self._condition.notify_all()


def request_json(base_url: str, method: str, path: str, body: object | None = None, timeout: int = 30) -> Any:
    data = None if body is None else json.dumps(body).encode()
    request = Request(f"{base_url}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status == 204:
                return None
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} failed with HTTP {error.code}: {detail}") from error


def free_port() -> int:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _merge_telemetry_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    durations = {name: {"values": [], "unavailable": 0} for name in DURATION_METRICS}
    counts = {name: 0 for name in COUNT_METRICS}
    ordered_agents = []
    for payload in payloads:
        for name in DURATION_METRICS:
            durations[name]["values"].extend(payload["durations_seconds"][name]["values"])
            durations[name]["unavailable"] += payload["durations_seconds"][name]["unavailable"]
        for name in COUNT_METRICS:
            counts[name] += payload["counts"][name]
        ordered_agents.extend(payload["ordered_agents"])
    return {
        "schema_version": 1,
        "status": "complete" if payloads and all(_workspace_telemetry_complete(payload) for payload in payloads) else "partial",
        "durations_seconds": durations,
        "counts": counts,
        "ordered_agents": ordered_agents,
    }


def _workspace_telemetry_complete(payload: dict[str, Any]) -> bool:
    if payload["status"] != "complete":
        return False
    counts = payload["counts"]
    durations = payload["durations_seconds"]
    if counts["serve_startups"] != 1 or counts["sessions"] < 1 or counts["primary_executions"] < counts["sessions"]:
        return False
    for name in ("fixture_setup", "environment_setup", "process_startup_to_health", "agent_inventory_loading", "cleanup", "total"):
        if len(durations[name]["values"]) != 1 or durations[name]["unavailable"] != 0:
            return False
    if len(durations["prompt_to_question"]["values"]) + len(durations["prompt_to_idle"]["values"]) != counts["sessions"]:
        return False
    if len(durations["answer_to_idle"]["values"]) != counts["primary_executions"] - counts["sessions"]:
        return False
    if len(durations["prompt_to_question"]["values"]) != len(durations["answer_to_idle"]["values"]):
        return False
    return len(durations["polling"]["values"]) == counts["primary_executions"] and all(durations[name]["unavailable"] == 0 for name in ("prompt_to_question", "answer_to_idle", "prompt_to_idle", "polling"))


class SystemWorkspace:
    def __init__(self, start_on_enter: bool = True, expected_request: str = "e2e"):
        self.timings: dict[str, list[float]] = {}
        self.duration_unavailable = {name: 0 for name in DURATION_METRICS}
        self._test_started_at = time.monotonic()
        self._start_attempted = False
        self._closed = False
        self._cleanup_started_at: float | None = None
        self._start_on_enter = start_on_enter
        telemetry_path = os.environ.get(TELEMETRY_PATH_ENV)
        self._telemetry_path = Path(telemetry_path).resolve() if telemetry_path else None
        self._telemetry_workspace_id = next(_TELEMETRY_WORKSPACE_IDS)
        self._telemetry_partial = False
        self.expected_request_target = Path("1_orchestrator") / expected_request
        self.process: subprocess.Popen[str] | None = None
        self.base_url = ""
        self._environment: dict[str, str] | None = None
        self.session_ids: list[str] = []
        self.serve_startup_count = 0
        self.primary_execution_count = 0
        self.task_call_count = 0
        self.successful_task_call_count = 0
        self.failed_task_call_count = 0
        self.incomplete_task_call_count = 0
        self.task_agent_names: list[str] = []
        try:
            with self._measure("fixture_setup"):
                self.temporary = tempfile.TemporaryDirectory(prefix="orchestrator-system-e2e-")
                self.root = Path(self.temporary.name)
                self.workspace = self.root / "workspace"
                self.workspace.mkdir()
                self.log_path = self.root / "opencode.log"
                self._write_fixture()
        except BaseException as error:
            self._telemetry_partial = True
            if hasattr(self, "temporary"):
                cleanup_started_at = time.monotonic()
                try:
                    self.temporary.cleanup()
                    self._record_timing("cleanup", cleanup_started_at)
                except BaseException as cleanup_error:
                    self.duration_unavailable["cleanup"] += 1
                    error.add_note(f"fixture cleanup failed: {cleanup_error}")
            self._record_timing("total", self._test_started_at)
            try:
                self._write_telemetry()
            except BaseException as telemetry_error:
                error.add_note(f"telemetry write failed: {telemetry_error}")
            raise

    @contextmanager
    def _measure(self, name: str) -> Iterator[None]:
        started_at = time.monotonic()
        try:
            yield
        finally:
            self._record_timing(name, started_at)

    def _record_timing(self, name: str, started_at: float) -> None:
        self.timings.setdefault(name, []).append(time.monotonic() - started_at)

    def timing_result(self) -> dict[str, Any]:
        return {
            "durations_seconds": {name: list(values) for name, values in self.timings.items()},
            "sessions_created": len(self.session_ids),
            "task_calls": self.task_call_count,
            "successful_task_calls": self.successful_task_call_count,
            "failed_task_calls": self.failed_task_call_count,
            "incomplete_task_calls": self.incomplete_task_call_count,
            "task_agent_names": list(self.task_agent_names),
        }

    def telemetry_result(self) -> dict[str, Any]:
        durations = {}
        for name in DURATION_METRICS:
            durations[name] = {"values": list(self.timings.get(name, [])), "unavailable": self.duration_unavailable.get(name, 0)}
        return {
            "schema_version": 1,
            "status": "partial" if getattr(self, "_telemetry_partial", False) else "complete",
            "durations_seconds": durations,
            "counts": {
                "serve_startups": getattr(self, "serve_startup_count", 0),
                "sessions": len(self.session_ids),
                "primary_executions": getattr(self, "primary_execution_count", 0),
                "task_attempts": self.task_call_count,
                "task_successes": self.successful_task_call_count,
                "task_failures": self.failed_task_call_count,
                "task_incomplete": self.incomplete_task_call_count,
            },
            "ordered_agents": list(self.task_agent_names),
        }

    def _write_telemetry(self) -> None:
        telemetry_path = getattr(self, "_telemetry_path", None)
        if telemetry_path is None:
            return
        contributions = _TELEMETRY_CONTRIBUTIONS.setdefault(telemetry_path, {})
        workspace_id = getattr(self, "_telemetry_workspace_id", None)
        if workspace_id is None:
            workspace_id = next(_TELEMETRY_WORKSPACE_IDS)
            self._telemetry_workspace_id = workspace_id
        contributions[workspace_id] = self.telemetry_result()
        telemetry = _merge_telemetry_payloads(list(contributions.values()))
        telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = telemetry_path.with_name(f".{telemetry_path.name}.{os.getpid()}.tmp")
        try:
            with temporary_path.open("w", encoding="utf-8") as output:
                json.dump(telemetry, output, ensure_ascii=False, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, telemetry_path)
        finally:
            temporary_path.unlink(missing_ok=True)


    def _isolated_environment(self) -> dict[str, str]:
        if self._environment is None:
            with self._measure("environment_setup"):
                self._environment = self._build_isolated_environment()
        return self._environment

    def _build_isolated_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        source_home = Path.home()
        source_config = Path(os.environ.get("OPENCODE_CONFIG_DIR", source_home / ".config/opencode")).expanduser().resolve()
        source_data = Path(os.environ.get("XDG_DATA_HOME", source_home / ".local/share")).expanduser().resolve()
        isolated_home = self.root / "home"
        isolated_data = self.root / "data-home"
        isolated_auth = isolated_data / "opencode/auth.json"
        isolated_home.mkdir()
        isolated_auth.parent.mkdir(parents=True)
        source_auth = source_data / "opencode/auth.json"
        if not source_auth.is_file():
            raise AssertionError(f"OpenCode authentication not found at {source_auth}")
        shutil.copy2(source_auth, isolated_auth)
        for variable in ("OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT", "OPENCODE_PERMISSION", "OPENCODE_PURE", "OPENCODE_SERVER_PASSWORD", "OPENCODE_SERVER_USERNAME"):
            environment.pop(variable, None)
        environment.update({
            "HOME": str(isolated_home),
            "XDG_CONFIG_HOME": str(self.root / "config-home"),
            "XDG_DATA_HOME": str(isolated_data),
            "XDG_STATE_HOME": str(self.root / "state-home"),
            "XDG_CACHE_HOME": str(self.root / "cache-home"),
            "OPENCODE_TEST_HOME": str(isolated_home),
            "OPENCODE_CONFIG_DIR": str(source_config),
            "OPENCODE_PURE": "1",
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
            "OPENCODE_DISABLE_AUTOCOMPACT": "1",
            "OPENCODE_DISABLE_MODELS_FETCH": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        environment["OPENCODE_CONFIG_CONTENT"] = json.dumps({"agent": self._agent_prompt_overrides()}, ensure_ascii=False)
        return environment

    def _write_fixture(self) -> None:
        agent_dir = self.workspace / ".opencode/agents"
        agent_dir.mkdir(parents=True)
        for source in (ROOT / "agents").glob("orchestrator-*.md"):
            shutil.copy2(source, agent_dir / source.name)
        (self.workspace / "AGENTS.md").write_text("# E2E fixture\n\nPlan changes only. Use Python standard-library conventions and `python3 -m unittest discover -s tests` for validation.\n", encoding="utf-8")
        (self.workspace / "src").mkdir()
        (self.workspace / "tests").mkdir()
        (self.workspace / "src/example.py").write_text("def current_value() -> int:\n    return 1\n", encoding="utf-8")
        (self.workspace / "tests/test_example.py").write_text("import unittest\n\nfrom src.example import current_value\n\n\nclass ExampleTests(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(current_value(), 1)\n", encoding="utf-8")

    def _agent_prompt_overrides(self) -> dict[str, dict[str, str]]:
        agents = {}
        for path in sorted((self.workspace / ".opencode/agents").glob("orchestrator-*.md")):
            parts = path.read_text(encoding="utf-8").split("---", 2)
            if len(parts) != 3:
                raise AssertionError(f"agent frontmatter missing: {path}")
            agents[path.stem] = {"prompt": parts[2].lstrip("\n")}
        return agents

    def start(self) -> None:
        if self._start_attempted:
            raise AssertionError("SystemWorkspace.start() may only be called once")
        self._start_attempted = True
        executable = shutil.which("opencode")
        if executable is None:
            raise AssertionError("opencode executable not found")
        port = free_port()
        self.base_url = f"http://127.0.0.1:{port}"
        log = self.log_path.open("w", encoding="utf-8")
        self._isolated_environment()
        with self._measure("process_startup_to_health"):
            self.serve_startup_count += 1
            self.process = subprocess.Popen([executable, "serve", "--hostname", "127.0.0.1", "--port", str(port), "--print-logs", "--log-level", "INFO"], cwd=self.workspace, env=self._isolated_environment(), stdout=log, stderr=subprocess.STDOUT, text=True)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise AssertionError(self.log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
                try:
                    health = request_json(self.base_url, "GET", "/global/health", timeout=2)
                    if isinstance(health, dict) and health.get("healthy") is True:
                        break
                except (OSError, RuntimeError, URLError):
                    time.sleep(1)
            else:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=10)
                log.flush()
                details = self.log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                raise AssertionError(f"opencode serve did not become healthy:\n{details}")
        with self._measure("agent_inventory_loading"):
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    agents = request_json(self.base_url, "GET", "/agent")
                    names = {agent.get("name") for agent in agents if isinstance(agent, dict)} if isinstance(agents, list) else set()
                    expected = {"orchestrator-analyst", "orchestrator-discovery", "orchestrator-stage-planner", "orchestrator-stage-reviewer"}
                    if not expected.issubset(names):
                        raise AssertionError(f"missing project agents: {sorted(expected - names)}")
                    return
                except (OSError, RuntimeError, URLError):
                    time.sleep(1)
        raise AssertionError("agent inventory did not load before startup deadline")

    def run_step(self, prompt: str, answer_labels: list[str] | None = None) -> list[dict[str, Any]]:
        before = capture_workspace_snapshot(self.workspace, self.expected_request_target)
        try:
            messages = self._run_step(prompt, answer_labels)
        except BaseException as error:
            try:
                assert_workspace_unchanged(before, capture_workspace_snapshot(self.workspace, self.expected_request_target))
            except Exception as guard_error:
                error.add_note(str(guard_error))
            raise
        assert_workspace_unchanged(before, capture_workspace_snapshot(self.workspace, self.expected_request_target))
        return messages

    def _run_step(self, prompt: str, answer_labels: list[str] | None = None) -> list[dict[str, Any]]:
        session = request_json(self.base_url, "POST", "/session", {"title": "orchestrator micro E2E"})
        if not isinstance(session, dict) or not isinstance(session.get("id"), str):
            raise AssertionError(f"unexpected session: {session}")
        session_id = session["id"]
        self.session_ids.append(session_id)
        with SessionEventWatcher(self.base_url, session_id) as event_watcher:
            return self._run_active_step(session_id, prompt, answer_labels, event_watcher)

    def _run_active_step(self, session_id: str, prompt: str, answer_labels: list[str] | None, event_watcher: SessionEventWatcher) -> list[dict[str, Any]]:
        prompt_started_at = time.monotonic()
        prompt_boundary = self._capture_assistant_boundary(session_id)
        prompt_idle_boundary = event_watcher.boundary()
        if answer_labels is not None:
            try:
                self.primary_execution_count += 1
                request_json(self.base_url, "POST", f"/session/{session_id}/prompt_async", {"agent": "orchestrator-analyst", "parts": [{"type": "text", "text": prompt}]})
                with self._measure("polling"):
                    question = self._wait_for_question(session_id)
            finally:
                self._record_timing("prompt_to_question", prompt_started_at)
            questions = question.get("questions")
            if not isinstance(questions, list) or len(questions) != len(answer_labels):
                raise AssertionError(f"unexpected questions: {question}")
            answers = [[label] for label in answer_labels]
            request_id = question.get("id")
            if not isinstance(request_id, str):
                raise AssertionError(f"question lacks id: {question}")
            path = f"/question/{request_id}/reply" if question.get("_transport") == "legacy" else f"/api/session/{session_id}/question/{request_id}/reply"
            reply_boundary = self._capture_assistant_boundary(session_id)
            reply_idle_boundary = event_watcher.boundary()
            idle_started_at = time.monotonic()
            try:
                self.primary_execution_count += 1
                request_json(self.base_url, "POST", path, {"answers": answers})
                with self._measure("polling"):
                    self._wait_for_idle(session_id, reply_boundary, event_watcher, reply_idle_boundary)
            finally:
                self._record_timing("answer_to_idle", idle_started_at)
                self._record_timing("prompt_or_answer_to_idle", idle_started_at)
        else:
            try:
                self.primary_execution_count += 1
                request_json(self.base_url, "POST", f"/session/{session_id}/prompt_async", {"agent": "orchestrator-analyst", "parts": [{"type": "text", "text": prompt}]})
                with self._measure("polling"):
                    self._wait_for_idle(session_id, prompt_boundary, event_watcher, prompt_idle_boundary)
            finally:
                self._record_timing("prompt_to_idle", prompt_started_at)
                self._record_timing("prompt_or_answer_to_idle", prompt_started_at)
        messages = request_json(self.base_url, "GET", f"/session/{session_id}/message")
        if not isinstance(messages, list):
            raise AssertionError(f"unexpected messages: {messages}")
        attempts = task_trace(messages)
        completed = successful_task_calls(messages)
        self.task_call_count += len(attempts)
        self.successful_task_call_count += len(completed)
        self.failed_task_call_count += len(failed_task_calls(messages))
        self.incomplete_task_call_count += len(incomplete_task_calls(messages))
        self.task_agent_names.extend(call.agent_name for call in completed if call.agent_name is not None)
        for call in attempts:
            if call.duration_seconds is None:
                self.duration_unavailable["subagent"] += 1
            else:
                self.timings.setdefault("subagent", []).append(call.duration_seconds)
        return messages

    def run_transition(self, prompt: str, answer_labels: list[str] | None = None) -> list[dict[str, Any]]:
        checkpoint = "E2E CHECKPOINT: complete one durable transition, persist its resulting state, then return WAITING_INPUT with action `continue test`."
        return self.run_step(f"{prompt}\n{checkpoint}", answer_labels)

    def _wait_for_question(self, session_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            response = request_json(self.base_url, "GET", f"/api/session/{session_id}/question")
            pending = response.get("data") if isinstance(response, dict) else None
            if isinstance(pending, list) and len(pending) == 1 and isinstance(pending[0], dict):
                return {**pending[0], "_transport": "v2"}
            legacy = request_json(self.base_url, "GET", "/question")
            owned = [item for item in legacy if isinstance(item, dict) and item.get("sessionID") == session_id] if isinstance(legacy, list) else []
            if len(owned) == 1:
                return {**owned[0], "_transport": "legacy"}
            time.sleep(1)
        raise AssertionError("native question did not appear")

    def _capture_assistant_boundary(self, session_id: str) -> dict[str, bool]:
        messages = request_json(self.base_url, "GET", f"/session/{session_id}/message")
        if not isinstance(messages, list):
            raise AssertionError(f"cannot capture assistant turn boundary: {messages!r}")
        return _assistant_message_boundary(messages)

    def _wait_for_idle(self, session_id: str, baseline: dict[str, bool] | frozenset[str], event_watcher: SessionEventWatcher, idle_boundary: int) -> None:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        use_wait = True
        wait_signaled = False
        last_diagnostic = "no status observed"
        while time.monotonic() < deadline:
            if use_wait:
                try:
                    request_json(self.base_url, "POST", f"/api/session/{session_id}/wait", timeout=10)
                    wait_signaled = True
                except TimeoutError:
                    pass
                except RuntimeError as error:
                    if "HTTP 503" not in str(error) or "Session wait is not available yet" not in str(error):
                        raise
                    use_wait = False
            statuses = request_json(self.base_url, "GET", "/session/status")
            status = statuses.get(session_id) if isinstance(statuses, dict) else None
            messages = request_json(self.base_url, "GET", f"/session/{session_id}/message")
            if not isinstance(messages, list):
                last_diagnostic = f"status={status!r}; messages={messages!r}"
                time.sleep(1)
                continue
            turn_terminal, turn_diagnostic = _new_assistant_turn_state(messages, baseline)
            explicitly_idle = isinstance(status, dict) and status.get("type") == "idle"
            event_idle = event_watcher.has_idle_after(idle_boundary)
            explicitly_active = isinstance(status, dict) and status.get("type") in ("busy", "retry")
            last_diagnostic = f"status={status!r}; wait_signaled={wait_signaled}; event_idle={event_idle}; {event_watcher.diagnostic(idle_boundary)}; {turn_diagnostic}"
            if turn_terminal and not explicitly_active and (wait_signaled or explicitly_idle or event_idle):
                return
            event_watcher.wait_for_event(1)
        raise AssertionError(f"session {session_id} did not become idle: {last_diagnostic}")

    def task_agents(self, messages: list[dict[str, Any]]) -> list[str]:
        return [call.agent_name for call in successful_task_calls(messages) if call.agent_name is not None]

    def assert_task_sequence(self, messages: list[dict[str, Any]], expected_agents: list[str]) -> list[TaskCall]:
        return assert_task_sequence(messages, expected_agents)

    def close(self) -> None:
        if self._closed:
            return
        if self._cleanup_started_at is None:
            self._cleanup_started_at = time.monotonic()
        if self.process is not None and self.process.poll() is None:
            for session_id in self.session_ids:
                try:
                    request_json(self.base_url, "DELETE", f"/session/{session_id}")
                except Exception:
                    pass
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        try:
            self.temporary.cleanup()
        except BaseException as cleanup_error:
            self._telemetry_partial = True
            if hasattr(self, "duration_unavailable"):
                self.duration_unavailable["cleanup"] += 1
                self.duration_unavailable["total"] += 1
            try:
                self._write_telemetry()
            except BaseException as telemetry_error:
                cleanup_error.add_note(f"telemetry write failed: {telemetry_error}")
            raise
        self._record_timing("cleanup", self._cleanup_started_at)
        self._record_timing("test_case_total", self._test_started_at)
        self.timings["total"] = list(self.timings["test_case_total"])
        self._write_telemetry()
        self._closed = True

    def __enter__(self):
        if not self._start_on_enter:
            return self
        try:
            self.start()
        except BaseException as error:
            self._telemetry_partial = True
            try:
                self.close()
            except Exception as cleanup_error:
                error.add_note(f"workspace cleanup failed: {cleanup_error}")
            raise
        return self

    def __exit__(self, _type, _value, _traceback):
        if _type is None:
            self.close()
        else:
            self._telemetry_partial = True
            try:
                self.close()
            except BaseException as cleanup_error:
                _value.add_note(f"workspace cleanup failed: {cleanup_error}")


def seed_plan(workspace: Path, stages: list[tuple[str, str]], current_stage: str, status: str = "planning") -> Path:
    target = workspace / "1_orchestrator/e2e"
    target.mkdir(parents=True, exist_ok=True)
    russian_titles = {"Value contract": "Контракт значения", "Value consumer": "Потребитель значения", "Value docs": "Документация значения", "Decoy value": "Ложное значение"}
    lines = ["---", f"status: {status}", f"current_stage: {current_stage}", "---", "", "# План", "", "## Outcome", "", "Сохранить проверяемый контракт API значения.", "", "## Decisions", "", "- Использовать существующие соглашения Python.", "", "## Stage map", ""]
    for index, (stage_status, title) in enumerate(stages, start=1):
        stage = f"S{index:02d}"
        dependency = "none" if index == 1 else f"S{index - 1:02d}"
        lines.extend([f"### {stage} — {russian_titles.get(title, title)}", f"- Status: {stage_status}", f"- Revision: {1 if stage_status in ('PLANNING', 'REVIEW', 'PASS') else 0}", f"- Depends on: {dependency}", "- Affected area: модуль значения", "- Primary risks: нарушение контракта возврата", f"- Consumes: {'none' if index == 1 else 'контракт значения'}", "- Produces: контракт значения", f"- Details: stages/{index:02d}-{title.lower().replace(' ', '-')}.md", f"- Review: reviews/{index:02d}.md", f"- Human review: stages/{index:02d}-{title.lower().replace(' ', '-')}.human-review.md", "- Human review revision: 0", "- Human review status: PENDING", f"- Human review review: reviews/{index:02d}-human-review.md", ""])
    plan = target / "plan.md"
    plan.write_text("\n".join(lines), encoding="utf-8")
    (target / "discovery.md").write_text("# Исследование\n\n- `src/example.py#current_value` — образец реализации.\n- `tests/test_example.py#ExampleTests` — образец тестирования.\n", encoding="utf-8")
    return plan


def write_passed_stage(workspace: Path, number: int, title: str) -> None:
    target = workspace / "1_orchestrator/e2e"
    (target / "stages").mkdir(exist_ok=True)
    (target / "reviews").mkdir(exist_ok=True)
    slug = title.lower().replace(" ", "-")
    russian_title = {"Value contract": "Контракт значения", "Value consumer": "Потребитель значения", "Value docs": "Документация значения", "Decoy value": "Ложное значение"}.get(title, title)
    (target / f"stages/{number:02d}-{slug}.md").write_text(f"---\nstage: S{number:02d}\nstatus: REVIEW\nrevision: 1\ndepends_on: []\n---\n\n# S{number:02d} — {russian_title}\n\n## Outcome\nКонтракт значения существует и проверяется.\n\n## Prerequisites\nНет.\n\n## Architecture\nСохранить API значения в существующей границе модуля.\n\n## Reference patterns\n- `src/example.py#current_value` — следовать существующему шаблону функции.\n\n## Required\n- Сохранить `current_value() == 1`, поскольку repository tests и потребители зависят от значения.\n\n## Key contracts\n### Consumes\nНет.\n### Produces\nПубличный контракт `current_value() -> int` независимо от наличия последующего этапа.\n\n## Risks\n- Изменение типа или значения возврата сломает потребителей; сохранить существующий контракт и проверить тестами.\n\n## Implementation outline\n- Сохранить существующий API значения и его проверку в текущей границе модуля.\n\n## Required test scenarios\n### Успешный контракт\n- Вход/предусловия: API доступен, входные данные отсутствуют.\n- Действие: вызвать `current_value()`.\n- Ожидаемый результат: возвращается целое число `1`, состояние не меняется.\n\n## Acceptance signals\n- `current_value()` возвращает `1`.\n\n## Verification\n- Сценарий контракта проверяется на unit-уровне.\n- `python3 -m unittest discover -s tests` завершается успешно.\n\n## Implementation discretion\n- Имена test cases, расположение тестов, fixtures и дополнительные тесты остаются реализации.\n", encoding="utf-8")
    (target / f"reviews/{number:02d}.md").write_text(f"---\nstage: S{number:02d}\nstage_revision: 1\nstatus: PASS\n---\n\n# Review S{number:02d}\n\n## Findings\n- Нет.\n", encoding="utf-8")


def write_passed_human_review(workspace: Path, number: int, title: str) -> None:
    target = workspace / "1_orchestrator/e2e"
    slug = title.lower().replace(" ", "-")
    russian_title = {"Value contract": "Контракт значения", "Value consumer": "Потребитель значения", "Value docs": "Документация значения", "Decoy value": "Ложное значение"}.get(title, title)
    (target / f"stages/{number:02d}-{slug}.human-review.md").write_text(f"---\nstage: S{number:02d}\nstatus: REVIEW\nrevision: 1\nsource_revision: 1\n---\n\n# S{number:02d} — {russian_title}\n\n## Что я получу после этапа\nБудет сохранён и подтверждён действующий контракт публичной операции `current_value()`: она возвращает целое число `1`.\n\n## Как это будет выглядеть в работе\n1. Пользователь или другая часть системы вызывает `current_value()` без входных данных.\n2. Операция возвращает `1`.\n3. Данные и состояние системы не изменяются.\n\n## Что именно будет сделано\n- Сохранён публичный контракт возврата целого числа `1`.\n- Сохранена автоматическая проверка этого результата.\n- Подтверждено отсутствие изменения состояния.\n- Проверена неизменность типа `int` и значения `1`, потому что их изменение нарушит контракт потребителей.\n\n## Чего после этапа ещё не будет\n- Дополнительных входных параметров.\n- Других возвращаемых значений.\n- Изменений данных или состояния.\n\n## Что важно подтвердить перед реализацией\nПовторное подтверждение не требуется: значение `1` и отсутствие изменения состояния уже утверждены техническим планом.\n\n## Как принять готовую реализацию\n- [ ] `current_value()` без входных данных возвращает целое число `1`.\n- [ ] Автоматические тесты проходят.\n- [ ] Состояние системы не меняется.\n\n## Статус\nТехнический план этапа проверен. Этот понятный план ожидает `APPROVE PLAN`; реализация ещё не началась. Контракт уже существует и должен быть сохранён без изменения пользовательского поведения.\n", encoding="utf-8")
    (target / f"reviews/{number:02d}-human-review.md").write_text(f"---\nstage: S{number:02d}\nstage_revision: 1\nsource_revision: 1\nstatus: PASS\n---\n\n# Review S{number:02d}\n\n## Findings\n- Нет.\n\n## Checks\n- Соответствие техническому плану: PASS\n- Итог этапа и практическая работа: PASS\n- Сценарии, ошибки и изменения состояния: PASS\n- Границы, риски и вопросы для подтверждения: PASS\n- Понятность без глубоких технических знаний: PASS\n", encoding="utf-8")
