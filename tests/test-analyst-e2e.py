#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, NoReturn, TextIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "opencode-agents.py"
TIMEOUT_SECONDS = int(os.environ.get("ANALYST_E2E_TIMEOUT_SECONDS", "1800"))
EXPECTED_ORCHESTRATOR_AGENTS = {
    "orchestrator-analyst",
    "orchestrator-executor",
    "orchestrator-final-reviewer",
    "orchestrator-plan-reviewer",
    "orchestrator-plan-ultra-reviewer",
    "orchestrator-stage-decomposer",
    "orchestrator-stage-pair-reviewer",
    "orchestrator-stage-question-reviewer",
    "orchestrator-task-adjuster",
    "orchestrator-task-executor",
    "orchestrator-task-planner",
    "orchestrator-task-reviewer",
}
ANALYST_SUBAGENTS = {
    "orchestrator-stage-decomposer",
    "orchestrator-stage-question-reviewer",
    "orchestrator-task-planner",
    "orchestrator-plan-reviewer",
    "orchestrator-stage-pair-reviewer",
}
EXPECTED_TASK_SEQUENCE = [
    "orchestrator-stage-decomposer",
    "orchestrator-stage-question-reviewer",
    "orchestrator-stage-decomposer",
    "orchestrator-task-planner",
    "orchestrator-plan-reviewer",
    "orchestrator-task-planner",
    "orchestrator-plan-reviewer",
    "orchestrator-stage-pair-reviewer",
    "orchestrator-task-planner",
]
PROMPT = """Подготовь план, не реализуй. Это CREATE: используй Target `1_orchestrator/analyst-e2e-bounds`, Lineage ID `analyst-e2e-bounds`, Generation `0`, Approval ID `analyst-e2e-bounds-g0`; существующий target не предоставлен, completed task paths — none. Ровно два этапа, без дополнительных этапов и без вопросов: все решения ниже окончательны.
S01: создать src/bounds.py с функцией clamp(value: int, lower: int, upper: int) -> int. Если lower > upper, поднять ValueError с точным сообщением lower must not exceed upper. Иначе вернуть lower для value < lower, upper для value > upper, иначе value. Создать tests/test_bounds.py на unittest: ниже, внутри, выше, равенство обеим границам, lower == upper, lower > upper и точное сообщение. Пути S01 только src/bounds.py и tests/test_bounds.py. Проверка: python3 -m unittest discover -s tests.
S02: создать src/bounds_batch.py с exact import `from src.bounds import clamp` и функцией clamp_all(values: Iterable[int], lower: int, upper: int) -> list[int], вызывающей clamp ровно один раз для каждого элемента. Сохранять порядок, поддержать пустой iterable и обычный одноразовый generator, propagating ValueError из clamp без изменения. Создать tests/test_bounds_batch.py на unittest: список; пустой iterable; native generator, проверяемый одним вызовом clamp_all; invalid bounds с точным сообщением; unittest.mock.patch для src.bounds_batch.clamp, доказывающий ordered one-call-per-element delegation и delegated return values; отдельный patched clamp, поднимающий заранее созданный ValueError, с assert что наружу вышел тот же exception object. Пути S02 только src/bounds_batch.py и tests/test_bounds_batch.py. Проверка: python3 -m unittest discover -s tests.
Порядок строго S01 затем S02. S02 execution prerequisite: task S01 должен завершиться COMPLETE/PASS; при planning/review до FINALIZE S01 ожидаемо DRAFT/PENDING, а его current stage PASS output authoritative. S02 использует публичный контракт clamp без изменения S01. Только Python standard library. Не менять README.md, AGENTS.md, src/__init__.py, tests/__init__.py, конфигурацию, зависимости или Git. Пользовательские approvals кроме общего approval плана не нужны. После approval создай task files, добейся PASS каждого stage с первого review, проверь пару S01+S02 с первого review и FINALIZE до READY. Executor не запускай."""


def fail(message: str) -> NoReturn:
    raise AssertionError(message)


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
    with socket.socket() as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        return int(server_socket.getsockname()[1])


def write_fixture(fixture: Path) -> None:
    (fixture / "src").mkdir(parents=True)
    (fixture / "tests").mkdir()
    (fixture / "AGENTS.md").write_text("# Fixture instructions\n\nPlan only. Do not implement product changes. Python uses standard library only. Tests run with `python3 -m unittest discover -s tests`.\n", encoding="utf-8")
    (fixture / "README.md").write_text("# Bounds fixture\n", encoding="utf-8")
    (fixture / "src/__init__.py").write_text("", encoding="utf-8")
    (fixture / "tests/__init__.py").write_text("", encoding="utf-8")


def wait_for_server(base_url: str, process: subprocess.Popen[str], log_path: Path) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            fail(f"opencode serve exited with {process.returncode}:\n{log_path.read_text(encoding='utf-8', errors='replace')[-4000:]}")
        try:
            health = request_json(base_url, "GET", "/global/health", timeout=2)
            if isinstance(health, dict) and health.get("healthy") is True:
                return
        except (OSError, RuntimeError, URLError):
            pass
        time.sleep(1)
    fail("opencode serve did not become healthy within 60 seconds")


def start_server(opencode: str, fixture: Path, environment: dict[str, str], log_file: TextIO, log_path: Path) -> tuple[subprocess.Popen[str], str]:
    for attempt in range(5):
        log_file.seek(0)
        log_file.truncate()
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        process = subprocess.Popen([opencode, "serve", "--pure", "--hostname", "127.0.0.1", "--port", str(port), "--print-logs", "--log-level", "INFO"], cwd=fixture, env=environment, stdout=log_file, stderr=subprocess.STDOUT, text=True)
        try:
            wait_for_server(base_url, process, log_path)
            return process, base_url
        except Exception:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            log_file.flush()
            log = log_path.read_text(encoding="utf-8", errors="replace")
            address_collision = "address already in use" in log.lower() or "eaddrinuse" in log.lower()
            if not address_collision or attempt == 4:
                raise
    fail("opencode serve failed to bind after five attempts")


def wait_for_idle(base_url: str, session_id: str, process: subprocess.Popen[str], log_path: Path) -> None:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_status = None
    last_text_count = 0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            fail(f"opencode serve exited with {process.returncode}:\n{log_path.read_text(encoding='utf-8', errors='replace')[-4000:]}")
        statuses = request_json(base_url, "GET", "/session/status")
        last_status = statuses.get(session_id) if isinstance(statuses, dict) else None
        messages = request_json(base_url, "GET", f"/session/{session_id}/message")
        if isinstance(messages, list):
            last_text_count = sum(1 for message in messages if isinstance(message, dict) and isinstance(message.get("info"), dict) and message["info"].get("role") == "assistant" and text_parts(message))
        active = isinstance(last_status, dict) and last_status.get("type") in ("busy", "retry")
        if last_text_count >= 2 and not active:
            return
        time.sleep(5)
    log = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
    fail(f"analyst session did not complete within {TIMEOUT_SECONDS} seconds; status={last_status}; assistant_texts={last_text_count}\nserver log:\n{log}")


def text_parts(message: dict[str, Any]) -> list[str]:
    parts = message.get("parts", [])
    if not isinstance(parts, list):
        return []
    return [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)]


def task_parts(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for message in messages:
        parts = message.get("parts", [])
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "tool" and part.get("tool") == "task":
                result.append(part)
    return result


def completed_task_output(part: dict[str, Any]) -> tuple[str, str, str]:
    state = part.get("state")
    if not isinstance(state, dict) or state.get("status") != "completed":
        fail(f"task call did not complete: {state}")
    task_input = state.get("input")
    if not isinstance(task_input, dict) or not isinstance(task_input.get("subagent_type"), str) or not isinstance(task_input.get("prompt"), str):
        fail(f"task call lacks subagent_type: {state}")
    output = state.get("output")
    if not isinstance(output, str):
        fail(f"task call lacks output: {state}")
    return task_input["subagent_type"], task_input["prompt"], output


def require_fields(text: str, expected: dict[str, str]) -> None:
    for field, value in expected.items():
        values = field_values(text, field)
        if values != [value]:
            fail(f"expected one exact `{field}: {value}`, got {values}:\n{text}")


def field_values(text: str, field: str) -> list[str]:
    normalized_lines = [line.strip() for line in text.splitlines()]
    return [line[len(field) + 2:] for line in normalized_lines if line.startswith(f"{field}: ")]


def single_field(text: str, field: str) -> str:
    values = field_values(text, field)
    if len(values) != 1:
        fail(f"expected one `{field}` field, got {values}:\n{text}")
    return values[0].strip().strip("`").strip()


def has_labeled_value(text: str, field: str, value: str) -> bool:
    return any(candidate.strip().strip("`").strip() == value for candidate in field_values(text, field))


def verify_task_sequence(parts: list[dict[str, Any]], approval_id: str, target: str, workflow_base: str) -> None:
    calls = [completed_task_output(part) for part in parts]
    all_subagents = [subagent for subagent, _, _ in calls]
    if any(subagent not in ANALYST_SUBAGENTS for subagent in all_subagents):
        fail(f"unexpected or executor subagent invoked: {all_subagents}")
    rejected_statuses = {"STAGE_DECOMPOSITION: REJECTED", "QUESTION_REVIEW: REJECTED", "PLANNING: REJECTED", "STAGE_REVIEW: REJECTED", "PAIR_REVIEW: REJECTED"}
    rejected_indices = [index for index, (_, _, output) in enumerate(calls) if rejected_statuses.intersection(line.strip() for line in output.splitlines())]
    if len(rejected_indices) > 3:
        fail(f"too many malformed-input retries: {len(rejected_indices)}")
    for index in rejected_indices:
        _, _, output = calls[index]
        rejection_values = [line.strip()[len("Rejection: "):] for line in output.splitlines() if line.strip().startswith("Rejection: ")]
        if len(rejection_values) != 1 or rejection_values[0] == "none":
            fail(f"rejected retry lacks one exact reason:\n{output}")
    accepted_calls = [call for index, call in enumerate(calls) if index not in rejected_indices]
    restage_indices = [index for index, (subagent, _, output) in enumerate(accepted_calls) if subagent == "orchestrator-stage-decomposer" and field_values(output, "MODE") == ["RESTAGE"]]
    if len(restage_indices) not in (1, 2):
        fail(f"expected one RESTAGE or one bounded regeneration, got {len(restage_indices)}")
    if len(restage_indices) == 2:
        if restage_indices != [2, 3]:
            fail(f"RESTAGE regeneration occurred out of order: {restage_indices}")
        del accepted_calls[restage_indices[0]]
    subagents = [subagent for subagent, _, _ in accepted_calls]
    prompts = [prompt for _, prompt, _ in accepted_calls]
    outputs = [output for _, _, output in accepted_calls]
    if subagents != EXPECTED_TASK_SEQUENCE:
        summaries = "\n---\n".join("\n".join(line for line in output.splitlines() if line.startswith(("STAGE_DECOMPOSITION:", "QUESTION_REVIEW:", "PLANNING:", "MODE:", "STAGE_REVIEW:", "PAIR_REVIEW:", "Stage ID:", "Stage revision:", "Pair ID:", "Rejection:"))) for output in outputs)
        revisions = "\n--- REVISE ---\n".join(output for output in outputs if any(line.strip().endswith(": REVISE") for line in output.splitlines()))
        if revisions:
            summaries = f"{summaries}\n--- REVISE DETAILS ---\n{revisions}"
        fail(f"unexpected analyst task sequence: {subagents}\n{summaries}")
    if len(outputs) != 9:
        fail(f"expected 9 accepted analyst task calls, got {len(outputs)}: {subagents}")
    require_fields(outputs[0], {"STAGE_DECOMPOSITION": "PASS", "MODE": "INITIAL", "Rejection": "none"})
    require_fields(outputs[1], {"QUESTION_REVIEW": "PASS_NO_QUESTIONS", "Rejection": "none"})
    require_fields(outputs[2], {"STAGE_DECOMPOSITION": "PASS", "MODE": "RESTAGE", "Stage count": "2", "Rejection": "none"})
    require_fields(outputs[3], {"PLANNING": "PASS", "MODE": "PLAN_STAGE", "Stage ID": "S01", "Stage revision": "1", "Rejection": "none"})
    require_fields(outputs[4], {"STAGE_REVIEW": "PASS", "Stage ID": "S01", "Stage revision": "1", "Rejection": "none"})
    require_fields(outputs[5], {"PLANNING": "PASS", "MODE": "PLAN_STAGE", "Stage ID": "S02", "Stage revision": "1", "Rejection": "none"})
    require_fields(outputs[6], {"STAGE_REVIEW": "PASS", "Stage ID": "S02", "Stage revision": "1", "Rejection": "none"})
    require_fields(outputs[7], {"PAIR_REVIEW": "PASS", "Pair ID": "S01+S02", "Rejection": "none"})
    require_fields(outputs[8], {"PLANNING": "PASS", "MODE": "FINALIZE", "Rejection": "none"})
    lineage_id = single_field(outputs[0], "Lineage ID")
    generation = single_field(outputs[0], "Generation")
    if lineage_id in ("", "none"):
        fail("analyst used empty lineage ID")
    if generation != "0":
        fail(f"CREATE workflow must use generation 0, got {generation}")
    for index, output in enumerate(outputs):
        if single_field(output, "Lineage ID") != lineage_id:
            fail("analyst task outputs use inconsistent lineage IDs")
        if single_field(output, "Generation") != generation:
            fail("analyst task outputs use inconsistent generations")
        if single_field(output, "Target") != target:
            fail("analyst task outputs use inconsistent targets")
        origins = field_values(output, "Origin")
        if origins != ["CREATE"]:
            fail(f"analyst task output omits or changes required origin: {origins}")
    if single_field(outputs[2], "Approval ID") != approval_id:
        fail("RESTAGE approval ID differs from approval output")
    for output in outputs[3:]:
        if single_field(output, "Approval ID") != approval_id:
            fail("post-approval task output uses inconsistent approval ID")
        if single_field(output, "Effective-contract ID") != approval_id:
            fail("post-approval task output uses inconsistent effective-contract ID")
    for index, prompt in enumerate(prompts):
        if not has_labeled_value(prompt, "WORKFLOW_BASE", workflow_base) or not has_labeled_value(prompt, "Lineage ID", lineage_id) or not has_labeled_value(prompt, "Generation", generation) or not has_labeled_value(prompt, "Origin", "CREATE"):
            fail(f"task prompt {index} lacks workflow identity")
        if index >= 1 and target not in prompt:
            fail(f"task prompt {index} lacks target")
        if index >= 3 and approval_id not in prompt:
            fail(f"post-approval task prompt {index} lacks approval ID")


def verify_messages(messages: list[dict[str, Any]], approval_message: str, approval_id: str, target: str) -> None:
    user_messages = []
    assistant_text_messages = []
    for message in messages:
        info = message.get("info")
        if not isinstance(info, dict):
            continue
        role = info.get("role")
        if role == "user":
            user_messages.append(message)
        elif role == "assistant" and text_parts(message):
            assistant_text_messages.append(message)
    if len(user_messages) != 2:
        fail(f"expected exactly two explicit user messages, got {len(user_messages)}")
    user_texts = ["\n".join(text_parts(message)) for message in user_messages]
    if user_texts != [PROMPT, approval_message]:
        fail(f"unexpected user turns: {user_texts}")
    if len(assistant_text_messages) != 2:
        fail(f"expected approval and READY assistant text messages, got {len(assistant_text_messages)}")
    approval_text, final_text = ["\n".join(text_parts(message)) for message in assistant_text_messages]
    for required in ("Итог: НУЖНО_ОДОБРЕНИЕ", "Запрос:", "Решения:", "Этапы:", "Результат:", "Границы:", "Зависимости:", "Пути:", "Контракты:", "Тесты:", "Порядок:", "Одобрения:", "Не цели:"):
        if required not in approval_text:
            fail(f"approval output lacks {required}:\n{approval_text}")
    for required in ("Итог: READY", "S01 revision 1 — PASS", "S02 revision 1 — PASS", "Действие: none"):
        if required not in final_text:
            fail(f"final output lacks {required}:\n{final_text}")
    if not any(line.startswith("Риски и ограничения: ") for line in final_text.splitlines()):
        fail(f"final output lacks risk field:\n{final_text}")
    for text in (approval_text, final_text):
        if single_field(text, "Target") != target:
            fail("assistant output uses inconsistent target")
        if single_field(text, "Approval ID") != approval_id:
            fail("assistant output uses inconsistent approval ID")
    all_parts = [part for message in messages for part in message.get("parts", []) if isinstance(part, dict)]
    if any(part.get("type") == "tool" and part.get("tool") == "question" for part in all_parts):
        fail("happy path unexpectedly invoked native question")


def workspace_snapshot(fixture: Path) -> dict[str, tuple[str, int, bytes]]:
    result = {}
    for path in sorted(fixture.rglob("*")):
        relative = path.relative_to(fixture)
        if relative.parts[0] == "1_orchestrator":
            continue
        mode = path.lstat().st_mode
        permissions = stat.S_IMODE(mode)
        if stat.S_ISDIR(mode):
            result[str(relative)] = ("directory", permissions, b"")
        elif stat.S_ISREG(mode):
            result[str(relative)] = ("file", permissions, path.read_bytes())
        elif stat.S_ISLNK(mode):
            result[str(relative)] = ("link", permissions, os.readlink(path).encode())
        else:
            result[str(relative)] = ("other", permissions, b"")
    return result


def verify_artifacts(fixture: Path, original_snapshot: dict[str, tuple[str, int, bytes]], approval_id: str, target: str) -> None:
    target_path = Path(target)
    if len(target_path.parts) != 2 or target_path.parts[0] != "1_orchestrator" or target_path.is_absolute():
        fail(f"invalid workflow target: {target}")
    workflow_root = fixture / "1_orchestrator"
    target_root = fixture / target_path
    target_entries = list(workflow_root.iterdir())
    if target_entries != [target_root]:
        fail(f"expected one workflow target, got {target_entries}")
    task_files = sorted((target_root / "tasks").glob("*.md"))
    if len(task_files) != 2:
        fail(f"expected exactly two task files, got {task_files}")
    for index, task_file in enumerate(task_files, start=1):
        content = task_file.read_text(encoding="utf-8")
        for required in (f"- Stage ID: S0{index}", "- Stage revision: 1", f"- Approval ID: {approval_id}", f"- Effective-contract ID: {approval_id}", "- Status: READY", "- Planning review: PASS", "- Result: NOT_STARTED"):
            if required not in content:
                fail(f"{task_file} lacks {required}")
    journal = target_root / "planning-issues.md"
    if not journal.is_file():
        fail(f"expected planning journal at {journal}")
    expected_files = {journal, *task_files}
    actual_files = {path for path in target_root.rglob("*") if path.is_file() or path.is_symlink()}
    if actual_files != expected_files:
        fail(f"unexpected workflow artifacts: {sorted(actual_files)}")
    expected_directories = {target_root / "tasks"}
    actual_directories = {path for path in target_root.rglob("*") if path.is_dir()}
    if actual_directories != expected_directories:
        fail(f"unexpected workflow directories: {sorted(actual_directories)}")
    final_snapshot = workspace_snapshot(fixture)
    if final_snapshot != original_snapshot:
        added = sorted(final_snapshot.keys() - original_snapshot.keys())
        removed = sorted(original_snapshot.keys() - final_snapshot.keys())
        changed = sorted(path for path in final_snapshot.keys() & original_snapshot.keys() if final_snapshot[path] != original_snapshot[path])
        fail(f"analyst changed product workspace: added={added}, removed={removed}, changed={changed}")


def run() -> None:
    opencode = shutil.which("opencode")
    if opencode is None:
        fail("opencode executable not found")
    with tempfile.TemporaryDirectory(prefix="opencode-analyst-e2e-") as temporary:
        temporary_root = Path(temporary)
        fixture = temporary_root / "fixture"
        fixture.mkdir()
        write_fixture(fixture)
        original_snapshot = workspace_snapshot(fixture)
        config_home = temporary_root / "config-home"
        config = config_home / "opencode"
        subprocess.run([sys.executable, str(CLI), "install", "--source", str(ROOT), "--target", str(config)], check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
        environment = os.environ.copy()
        for variable in ("OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT", "OPENCODE_PERMISSION", "OPENCODE_SERVER_PASSWORD", "OPENCODE_SERVER_USERNAME"):
            environment.pop(variable, None)
        data_home = temporary_root / "data-home"
        auth_directory = data_home / "opencode"
        auth_directory.mkdir(parents=True)
        source_data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        source_auth = source_data_home / "opencode/auth.json"
        if not source_auth.is_file():
            fail(f"OpenCode authentication not found at {source_auth}")
        shutil.copy2(source_auth, auth_directory / "auth.json")
        isolated_home = temporary_root / "home"
        isolated_home.mkdir()
        environment["HOME"] = str(isolated_home)
        environment["XDG_CONFIG_HOME"] = str(config_home)
        environment["XDG_DATA_HOME"] = str(data_home)
        environment["XDG_STATE_HOME"] = str(temporary_root / "state-home")
        environment["XDG_CACHE_HOME"] = str(temporary_root / "cache-home")
        environment["OPENCODE_CONFIG_DIR"] = str(config)
        environment["OPENCODE_DISABLE_CLAUDE_CODE"] = "1"
        environment["OPENCODE_DISABLE_CLAUDE_CODE_PROMPT"] = "1"
        environment["OPENCODE_DISABLE_CLAUDE_CODE_SKILLS"] = "1"
        log_path = temporary_root / "server.log"
        session_id = None
        with log_path.open("w", encoding="utf-8") as log_file:
            process, base_url = start_server(opencode, fixture, environment, log_file, log_path)
            try:
                wait_for_server(base_url, process, log_path)
                agents = request_json(base_url, "GET", "/agent")
                if not isinstance(agents, list):
                    fail(f"unexpected /agent response: {agents}")
                orchestrator_agents: set[str] = set()
                for agent in agents:
                    if isinstance(agent, dict) and isinstance(agent.get("name"), str) and agent["name"].startswith("orchestrator-"):
                        orchestrator_agents.add(agent["name"])
                if orchestrator_agents != EXPECTED_ORCHESTRATOR_AGENTS:
                    fail(f"unexpected orchestrator inventory: {sorted(orchestrator_agents)}")
                session = request_json(base_url, "POST", "/session", {"title": "Analyst native-loop E2E"})
                if not isinstance(session, dict) or not isinstance(session.get("id"), str):
                    fail(f"unexpected session response: {session}")
                session_id = session["id"]
                approval_response = request_json(base_url, "POST", f"/session/{session_id}/message", {"agent": "orchestrator-analyst", "parts": [{"type": "text", "text": PROMPT}]}, timeout=TIMEOUT_SECONDS)
                if not isinstance(approval_response, dict):
                    fail(f"unexpected approval response: {approval_response}")
                approval_text = "\n".join(text_parts(approval_response))
                approval_id = single_field(approval_text, "Approval ID")
                target = single_field(approval_text, "Target")
                if (fixture / "1_orchestrator").exists():
                    fail("analyst wrote workflow artifacts before approval")
                approval_message = f"APPROVE {approval_id}"
                request_json(base_url, "POST", f"/session/{session_id}/prompt_async", {"agent": "orchestrator-analyst", "parts": [{"type": "text", "text": approval_message}]})
                wait_for_idle(base_url, session_id, process, log_path)
                messages = request_json(base_url, "GET", f"/session/{session_id}/message")
                if not isinstance(messages, list) or not all(isinstance(message, dict) for message in messages):
                    fail(f"unexpected messages response: {messages}")
                verify_task_sequence(task_parts(messages), approval_id, target, str(fixture))
                verify_messages(messages, approval_message, approval_id, target)
                verify_artifacts(fixture, original_snapshot, approval_id, target)
            except Exception as error:
                log_file.flush()
                log = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                raise AssertionError(f"{error}\nserver log:\n{log}") from error
            finally:
                cleanup_error = None
                if session_id is not None and process.poll() is None:
                    try:
                        request_json(base_url, "DELETE", f"/session/{session_id}")
                    except Exception as error:
                        cleanup_error = error
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                if cleanup_error is not None and sys.exc_info()[0] is None:
                    raise RuntimeError(f"failed to delete analyst E2E session: {cleanup_error}") from cleanup_error


if __name__ == "__main__":
    run()
    print("Analyst E2E passed")
