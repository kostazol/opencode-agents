from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
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


@dataclass(frozen=True)
class TaskCall:
    agent_name: str | None
    call_id: str | None
    order: int
    input: dict[str, Any] | None
    status: str
    output: str | None
    error: str | None
    compact_result: str | None

    @property
    def successful(self) -> bool:
        return self.agent_name in TASK_AGENTS and self.status == "completed" and self.error is None

    @property
    def failed(self) -> bool:
        return self.status == "error" or self.error is not None

    @property
    def incomplete(self) -> bool:
        return not self.successful and not self.failed


@dataclass(frozen=True)
class WorkspaceEntry:
    kind: str
    digest_or_target: str | None


@dataclass(frozen=True)
class WorkspaceSnapshot:
    root: Path
    allowed_target: Path
    entries: dict[Path, WorkspaceEntry]
    workflow_targets: frozenset[Path]
    git_status: str


def capture_workspace_snapshot(root: Path, allowed_target: Path) -> WorkspaceSnapshot:
    root = root.resolve()
    if allowed_target.is_absolute():
        raise AssertionError(f"allowed request target must be relative: {allowed_target}")
    canonical_target = Path(os.path.normpath(str(allowed_target)))
    if canonical_target.parts[:1] != ("1_orchestrator",) or len(canonical_target.parts) != 2 or canonical_target.parts[1] in ("", ".", ".."):
        raise AssertionError(f"allowed request target must be exact 1_orchestrator/<request>: {allowed_target}")
    entries = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[:2] == (".opencode", "node_modules"):
            continue
        if relative in (Path(".opencode/package.json"), Path(".opencode/package-lock.json")):
            continue
        if path.is_symlink():
            entries[relative] = WorkspaceEntry("symlink", os.readlink(path))
        elif path.is_dir():
            entries[relative] = WorkspaceEntry("directory", None)
        elif path.is_file():
            entries[relative] = WorkspaceEntry("file", hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            entries[relative] = WorkspaceEntry("other", None)
    orchestrator = root / "1_orchestrator"
    workflow_targets = frozenset(path.relative_to(root) for path in orchestrator.iterdir() if path.is_dir()) if orchestrator.is_dir() else frozenset()
    return WorkspaceSnapshot(root, canonical_target, entries, workflow_targets, _git_status(root, canonical_target))


def assert_workspace_unchanged(before: WorkspaceSnapshot, after: WorkspaceSnapshot) -> None:
    if before.root != after.root or before.allowed_target != after.allowed_target:
        raise AssertionError(f"workspace snapshot identity mismatch: before={before}; after={after}")
    changed = []
    for path in sorted(before.entries.keys() | after.entries.keys()):
        if before.entries.get(path) == after.entries.get(path):
            continue
        if _is_allowed_workspace_change(path, before.entries.get(path), after.entries.get(path), before.allowed_target):
            continue
        changed.append(f"{path}: {before.entries.get(path)!r} -> {after.entries.get(path)!r}")
    unexpected_targets = sorted(target for target in after.workflow_targets - before.workflow_targets if target != before.allowed_target)
    if unexpected_targets:
        changed.append(f"unexpected workflow targets: {unexpected_targets!r}")
    if before.git_status != after.git_status:
        changed.append(f"git status changed: {before.git_status!r} -> {after.git_status!r}")
    if changed:
        raise AssertionError("product workspace mutation detected:\n" + "\n".join(changed))


def _is_allowed_workspace_change(path: Path, before: WorkspaceEntry | None, after: WorkspaceEntry | None, allowed_target: Path) -> bool:
    if path == allowed_target or allowed_target in path.parents:
        return True
    if path in allowed_target.parents and before is None and after == WorkspaceEntry("directory", None):
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


def task_trace(messages: list[dict[str, Any]]) -> list[TaskCall]:
    result = []
    for message in messages:
        for part in message.get("parts", []):
            if not isinstance(part, dict) or part.get("type") != "tool" or part.get("tool") != "task":
                continue
            state = part.get("state")
            task_input = state.get("input") if isinstance(state, dict) else None
            output = state.get("output") if isinstance(state, dict) and isinstance(state.get("output"), str) else None
            raw_error = state.get("error") if isinstance(state, dict) else None
            error = raw_error if isinstance(raw_error, str) else repr(raw_error) if raw_error is not None else None
            status = state.get("status") if isinstance(state, dict) else None
            result.append(TaskCall(
                agent_name=task_input.get("subagent_type") if isinstance(task_input, dict) and isinstance(task_input.get("subagent_type"), str) else None,
                call_id=part.get("callID") if isinstance(part.get("callID"), str) else None,
                order=len(result),
                input=task_input if isinstance(task_input, dict) else None,
                status=status if isinstance(status, str) else "unknown",
                output=output,
                error=error,
                compact_result=output,
            ))
    return result


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


class SystemWorkspace:
    def __init__(self, start_on_enter: bool = True, expected_request: str = "e2e"):
        self.timings: dict[str, list[float]] = {}
        self._test_started_at = time.monotonic()
        self._start_attempted = False
        self._closed = False
        self._cleanup_started_at: float | None = None
        self._start_on_enter = start_on_enter
        self.expected_request_target = Path("1_orchestrator") / expected_request
        self.process: subprocess.Popen[str] | None = None
        self.base_url = ""
        self._environment: dict[str, str] | None = None
        self.session_ids: list[str] = []
        self.task_call_count = 0
        self.successful_task_call_count = 0
        self.failed_task_call_count = 0
        self.incomplete_task_call_count = 0
        self.task_agent_names: list[str] = []
        with self._measure("fixture_setup"):
            self.temporary = tempfile.TemporaryDirectory(prefix="orchestrator-system-e2e-")
            self.root = Path(self.temporary.name)
            self.workspace = self.root / "workspace"
            self.workspace.mkdir()
            self.log_path = self.root / "opencode.log"
            self._write_fixture()

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
        prompt_started_at = time.monotonic()
        if answer_labels is not None:
            try:
                request_json(self.base_url, "POST", f"/session/{session_id}/prompt_async", {"agent": "orchestrator-analyst", "parts": [{"type": "text", "text": prompt}]})
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
            idle_started_at = time.monotonic()
            try:
                request_json(self.base_url, "POST", path, {"answers": answers})
                self._wait_for_idle(session_id)
            finally:
                self._record_timing("answer_to_idle", idle_started_at)
                self._record_timing("prompt_or_answer_to_idle", idle_started_at)
        else:
            try:
                request_json(self.base_url, "POST", f"/session/{session_id}/prompt_async", {"agent": "orchestrator-analyst", "parts": [{"type": "text", "text": prompt}]})
                self._wait_for_idle(session_id)
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

    def _wait_for_idle(self, session_id: str) -> None:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        use_wait = True
        while time.monotonic() < deadline:
            if use_wait:
                try:
                    request_json(self.base_url, "POST", f"/api/session/{session_id}/wait", timeout=10)
                except TimeoutError:
                    continue
                except RuntimeError as error:
                    if "HTTP 503" not in str(error) or "Session wait is not available yet" not in str(error):
                        raise
                    use_wait = False
            statuses = request_json(self.base_url, "GET", "/session/status")
            status = statuses.get(session_id) if isinstance(statuses, dict) else None
            messages = request_json(self.base_url, "GET", f"/session/{session_id}/message")
            has_completed_assistant = isinstance(messages, list) and any(isinstance(message, dict) and isinstance(message.get("info"), dict) and message["info"].get("role") == "assistant" and isinstance(message["info"].get("time"), dict) and message["info"]["time"].get("completed") is not None for message in messages)
            tasks_terminal = isinstance(messages, list) and all(call.status in ("completed", "error") for call in task_trace(messages))
            if has_completed_assistant and tasks_terminal and (not isinstance(status, dict) or status.get("type") == "idle"):
                return
            time.sleep(1)
        raise AssertionError("session did not become idle")

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
        self.temporary.cleanup()
        self._record_timing("cleanup", self._cleanup_started_at)
        self._record_timing("test_case_total", self._test_started_at)
        self._closed = True

    def __enter__(self):
        if not self._start_on_enter:
            return self
        try:
            self.start()
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise
        return self

    def __exit__(self, _type, _value, _traceback):
        if _type is None:
            self.close()
        else:
            try:
                self.close()
            except BaseException:
                pass


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
