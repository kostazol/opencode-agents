#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import ModuleType
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[1]
PROMPT = """Подготовь план, не реализуй. Это CREATE: используй Target `1_orchestrator/replanning-e2e`, Lineage ID `replanning-e2e`, Generation `0`, Approval ID `replanning-e2e-g0`; существующий target не предоставлен, completed task paths — none. Ровно один этап, без вопросов: все решения окончательны.
S01: создать src/slug.py с функцией slug(value: str) -> str, которая strips leading/trailing whitespace, lowercases ASCII letters, replaces each maximal non-alphanumeric run with one hyphen, strips boundary hyphens, а для результата без alphanumeric characters поднимает ValueError с точным сообщением `slug must contain an alphanumeric character`. Создать tests/test_slug.py на unittest: mixed case/whitespace, repeated separators, boundary separators, digits, empty input, punctuation-only input и точное сообщение ошибки. Пути только src/slug.py и tests/test_slug.py. Проверка: python3 -m unittest discover -s tests. Только Python standard library. Не менять другие product files, конфигурацию, зависимости или Git.
Обязательный regression trace controller: PLAN_STAGE создаёт ровно один task revision 1. Первый fresh stage review возвращает `STAGE_REVIEW: REVISE`, `Stage revision: 1`, finding signature `REPLAN-E2E-EMPTY-ERROR-CASE` и `Блокер: none`: task revision 1 намеренно не закрепляет punctuation-only input и exact ValueError message в Test work. Analyst не останавливается и не просит пользователя повторить планирование. Он немедленно вызывает planner `REVISE_STAGE` с complete approved RESTAGE, exact current planner PASS и exact reviewer REVISE verbatim. Planner добавляет missing test obligation, повышает revision до 2. Следующий fresh review возвращает PASS revision 2. Затем FINALIZE до READY в том же runner turn. Executor не запускать."""
EXPECTED_SEQUENCE = [
    "orchestrator-stage-decomposer",
    "orchestrator-stage-question-reviewer",
    "orchestrator-stage-decomposer",
    "orchestrator-task-planner",
    "orchestrator-plan-reviewer",
    "orchestrator-task-planner",
    "orchestrator-plan-reviewer",
    "orchestrator-task-planner",
]


def fail(message: str) -> NoReturn:
    raise AssertionError(message)


def load_e2e() -> ModuleType:
    path = Path(__file__).with_name("test-analyst-e2e.py")
    spec = importlib.util.spec_from_file_location("analyst_e2e_common", path)
    if spec is None or spec.loader is None:
        fail(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract_payload(output: str) -> str:
    text = output
    if "<task_result>" in text and "</task_result>" in text:
        text = text.split("<task_result>", 1)[1].split("</task_result>", 1)[0]
    lines = [line for line in text.strip().splitlines() if not line.strip().startswith("```")]
    return "\n".join(lines).strip()


def accepted_calls(e2e: ModuleType, messages: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    calls = [e2e.completed_task_output(part) for part in e2e.task_parts(messages)]
    if any(call[0] == "orchestrator-stage-pair-reviewer" for call in calls):
        fail("one-stage replanning flow invoked pair reviewer")
    rejected_statuses = {f"{contract}: REJECTED" for contract in ("STAGE_DECOMPOSITION", "QUESTION_REVIEW", "PLANNING", "STAGE_REVIEW", "PAIR_REVIEW")}
    rejected = []
    accepted = []
    for index, call in enumerate(calls):
        subagent, _, output = call
        if subagent not in e2e.ANALYST_SUBAGENTS:
            fail(f"unexpected or executor subagent invoked: {subagent}")
        if any(line.strip().endswith(": BLOCKED") for line in output.splitlines()) and not e2e.retryable_blocked_output(output):
            fail(f"substantive BLOCKED output cannot be retried:\n{output}")
        if rejected_statuses.intersection(line.strip() for line in output.splitlines()) or e2e.retryable_blocked_output(output) or e2e.malformed_contract_output(output) or e2e.ambiguous_contract_output(subagent, output):
            rejected.append(call)
            contract_roles = {"STAGE_DECOMPOSITION": "orchestrator-stage-decomposer", "QUESTION_REVIEW": "orchestrator-stage-question-reviewer", "PLANNING": "orchestrator-task-planner", "STAGE_REVIEW": "orchestrator-plan-reviewer", "PAIR_REVIEW": "orchestrator-stage-pair-reviewer"}
            emitted_contracts = [contract for contract in contract_roles if e2e.field_values(output, contract)]
            intended = contract_roles[emitted_contracts[0]] if len(emitted_contracts) == 1 and contract_roles[emitted_contracts[0]] != subagent else subagent
            if index + 1 >= len(calls) or calls[index + 1][0] != intended:
                fail(f"malformed call was not retried immediately by intended role: {subagent} -> {intended}")
            current_mode = e2e.field_values(output, "MODE")
            next_mode = e2e.field_values(calls[index + 1][2], "MODE")
            if current_mode and next_mode and current_mode != next_mode:
                fail(f"malformed retry changed logical mode: {current_mode} -> {next_mode}")
            if contract_payload(output) not in calls[index + 1][1]:
                fail("malformed retry prompt omits exact rejected output")
        else:
            accepted.append(call)
    if len(rejected) > 3:
        fail(f"too many malformed-input retries: {len(rejected)}")
    canonical = []
    equivalent_replays = 0
    for call in accepted:
        if canonical and e2e.task_phase(call[0], call[2]) == e2e.task_phase(canonical[-1][0], canonical[-1][2]):
            if not e2e.equivalent_contract_identity(canonical[-1][2], call[2]):
                fail(f"conflicting accepted logical phase replay: {e2e.task_phase(call[0], call[2])}")
            equivalent_replays += 1
            canonical[-1] = call
        else:
            canonical.append(call)
    if equivalent_replays > 3:
        fail(f"too many equivalent accepted phase replays: {equivalent_replays}")
    return canonical


def verify_trace(e2e: ModuleType, messages: list[dict[str, Any]], approval_id: str, target: str, workflow_base: str) -> None:
    calls = accepted_calls(e2e, messages)
    subagents = [subagent for subagent, _, _ in calls]
    prompts = [prompt for _, prompt, _ in calls]
    outputs = [output for _, _, output in calls]
    if subagents != EXPECTED_SEQUENCE:
        fail(f"unexpected replanning sequence: {subagents}")
    expected_fields = (
        (0, {"STAGE_DECOMPOSITION": "PASS", "MODE": "INITIAL", "Stage count": "1"}),
        (1, {"QUESTION_REVIEW": "PASS_NO_QUESTIONS"}),
        (2, {"STAGE_DECOMPOSITION": "PASS", "MODE": "RESTAGE", "Stage count": "1", "Approval ID": approval_id}),
        (3, {"PLANNING": "PASS", "MODE": "PLAN_STAGE", "Stage ID": "S01", "Stage revision": "1"}),
        (4, {"STAGE_REVIEW": "REVISE", "Stage ID": "S01", "Stage revision": "1", "Блокер": "none"}),
        (5, {"PLANNING": "PASS", "MODE": "REVISE_STAGE", "Stage ID": "S01", "Stage revision": "2"}),
        (6, {"STAGE_REVIEW": "PASS", "Stage ID": "S01", "Stage revision": "2", "Блокер": "none"}),
        (7, {"PLANNING": "PASS", "MODE": "FINALIZE"}),
    )
    for index, fields in expected_fields:
        e2e.require_fields(outputs[index], fields)
    if "REPLAN-E2E-EMPTY-ERROR-CASE" not in outputs[4]:
        fail("first stage review lacks required regression finding")
    for index, output in enumerate(outputs):
        if e2e.single_field(output, "Lineage ID") != "replanning-e2e" or e2e.single_field(output, "Generation") != "0" or e2e.single_field(output, "Target") != target:
            fail(f"workflow identity mismatch in output {index}")
    for index in range(3, len(outputs)):
        if e2e.single_field(outputs[index], "Approval ID") != approval_id or e2e.single_field(outputs[index], "Effective-contract ID") != approval_id:
            fail(f"post-approval contract identity mismatch in output {index}")
    for index, prompt in enumerate(prompts):
        if not e2e.has_labeled_value(prompt, "WORKFLOW_BASE", workflow_base) or not e2e.has_labeled_value(prompt, "Lineage ID", "replanning-e2e") or not e2e.has_labeled_value(prompt, "Generation", "0") or not e2e.has_labeled_value(prompt, "Origin", "CREATE"):
            fail(f"task prompt {index} lacks workflow identity")
    restage = contract_payload(outputs[2])
    planner_v1 = contract_payload(outputs[3])
    revise = contract_payload(outputs[4])
    planner_v2 = contract_payload(outputs[5])
    missing = [name for name, payload in (("RESTAGE", restage), ("planner PASS", planner_v1), ("reviewer REVISE", revise)) if payload not in prompts[5]]
    if missing:
        fail(f"REVISE_STAGE handoff omits verbatim payloads {missing}\nPROMPT:\n{prompts[5]}")
    if restage not in prompts[6] or planner_v2 not in prompts[6]:
        fail("revision-2 review handoff does not preserve complete RESTAGE and planner PASS verbatim")
    review_v2 = contract_payload(outputs[6])
    finalize_missing = [name for name, payload in (("RESTAGE", restage), ("planner revision 2", planner_v2), ("stage-review PASS", review_v2)) if payload not in prompts[7]]
    if finalize_missing:
        fail(f"FINALIZE handoff omits verbatim payloads {finalize_missing}\nPROMPT:\n{prompts[7]}")
    if f"APPROVE {approval_id}" not in prompts[7] or "Pair PASS results: none" not in prompts[7]:
        fail("FINALIZE handoff lacks exact approval command or one-stage pair evidence none")


def verify_messages(e2e: ModuleType, messages: list[dict[str, Any]], approval_message: str, approval_id: str, target: str) -> None:
    user_texts = ["\n".join(e2e.text_parts(message)) for message in messages if isinstance(message.get("info"), dict) and message["info"].get("role") == "user"]
    if user_texts != [PROMPT, approval_message]:
        fail(f"unexpected or synthetic user turns: {user_texts}")
    all_parts = [part for message in messages for part in message.get("parts", []) if isinstance(part, dict)]
    if any(part.get("type") == "tool" and part.get("tool") == "question" for part in all_parts):
        fail("replanning flow unexpectedly invoked native question")
    texts = ["\n".join(e2e.text_parts(message)) for message in messages if isinstance(message.get("info"), dict) and message["info"].get("role") == "assistant" and e2e.text_parts(message)]
    approval = [text for text in texts if "Итог: НУЖНО_ОДОБРЕНИЕ" in text]
    ready = [text for text in texts if "Итог: READY" in text]
    blocked = [text for text in texts if "Итог: BLOCKED" in text]
    if len(approval) != 1 or len(ready) != 1 or blocked:
        fail(f"expected approval then READY without blocker: {texts}")
    for text in (approval[0], ready[0]):
        if e2e.single_field(text, "Approval ID") != approval_id or e2e.single_field(text, "Target") != target:
            fail("assistant response identity mismatch")
    if "S01 revision 2 — PASS" not in ready[0] or "Действие: none" not in ready[0]:
        fail(f"READY response lacks revised PASS: {ready[0]}")


def verify_artifacts(e2e: ModuleType, fixture: Path, original_snapshot: dict[str, tuple[str, int, bytes]], approval_id: str, target: str) -> None:
    target_root = fixture / target
    workflow_root = fixture / "1_orchestrator"
    if list(workflow_root.iterdir()) != [target_root]:
        fail(f"expected sole workflow target {target_root}")
    task_files = sorted((target_root / "tasks").glob("*.md"))
    if len(task_files) != 1:
        fail(f"expected one task file, got {task_files}")
    content = task_files[0].read_text(encoding="utf-8")
    for required in ("- Stage ID: S01", "- Stage revision: 2", f"- Approval ID: {approval_id}", f"- Effective-contract ID: {approval_id}", "- Status: READY", "- Planning review: PASS", "- Result: NOT_STARTED"):
        if required not in content:
            fail(f"{task_files[0]} lacks {required}")
    test_work_parts = content.split("## Test work", 1)
    if len(test_work_parts) != 2:
        fail(f"{task_files[0]} lacks Test work section")
    test_work = test_work_parts[1].split("## ", 1)[0]
    for required in ("punctuation-only", "slug must contain an alphanumeric character"):
        if required not in test_work:
            fail(f"{task_files[0]} Test work lacks {required}")
    journal = target_root / "planning-issues.md"
    actual_files = {path for path in target_root.rglob("*") if path.is_file() or path.is_symlink()}
    if actual_files != {journal, task_files[0]}:
        fail(f"unexpected workflow artifacts: {sorted(actual_files)}")
    if e2e.workspace_snapshot(fixture) != original_snapshot:
        fail("analyst changed product workspace")


def run() -> None:
    e2e = load_e2e()
    opencode = shutil.which("opencode")
    if opencode is None:
        fail("opencode executable not found")
    with tempfile.TemporaryDirectory(prefix="opencode-analyst-replanning-e2e-") as temporary:
        temporary_root = Path(temporary)
        fixture = temporary_root / "fixture"
        fixture.mkdir()
        e2e.write_fixture(fixture)
        original_snapshot = e2e.workspace_snapshot(fixture)
        config_home = temporary_root / "config-home"
        config = config_home / "opencode"
        subprocess.run([sys.executable, str(e2e.CLI), "install", "--source", str(ROOT), "--target", str(config)], check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
        data_home = temporary_root / "data-home"
        auth_directory = data_home / "opencode"
        auth_directory.mkdir(parents=True)
        source_data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        source_auth = source_data_home / "opencode/auth.json"
        if not source_auth.is_file():
            fail(f"OpenCode authentication not found at {source_auth}")
        shutil.copy2(source_auth, auth_directory / "auth.json")
        environment = e2e.isolated_environment(config, temporary_root, data_home)
        log_path = temporary_root / "server.log"
        session_id = None
        started = time.monotonic()
        checkpoints = {}
        timing_emitted = False
        with log_path.open("w", encoding="utf-8") as log_file:
            process, base_url = e2e.start_server(opencode, fixture, environment, log_file, log_path)
            try:
                session = e2e.request_json(base_url, "POST", "/session", {"title": "Analyst replanning E2E"})
                if not isinstance(session, dict) or not isinstance(session.get("id"), str):
                    fail(f"unexpected session response: {session}")
                session_id = session["id"]
                deadline = time.monotonic() + e2e.TIMEOUT_SECONDS
                e2e.request_json(base_url, "POST", f"/session/{session_id}/prompt_async", {"agent": "orchestrator-analyst", "parts": [{"type": "text", "text": PROMPT}]})
                _, approval_text = e2e.wait_for_approval(base_url, session_id, process, log_path, deadline)
                checkpoints["approval"] = time.monotonic()
                approval_id = e2e.single_field(approval_text, "Approval ID")
                target = e2e.single_field(approval_text, "Target")
                if approval_id != "replanning-e2e-g0" or target != "1_orchestrator/replanning-e2e":
                    fail(f"unexpected approval identity: {approval_id}, {target}")
                if (fixture / "1_orchestrator").exists():
                    fail("analyst wrote workflow artifacts before approval")
                approval_message = f"APPROVE {approval_id}"
                e2e.request_json(base_url, "POST", f"/session/{session_id}/prompt_async", {"agent": "orchestrator-analyst", "parts": [{"type": "text", "text": approval_message}]})
                e2e.wait_for_idle(base_url, session_id, process, log_path, deadline)
                checkpoints["ready"] = time.monotonic()
                messages = e2e.request_json(base_url, "GET", f"/session/{session_id}/message")
                if not isinstance(messages, list) or not all(isinstance(message, dict) for message in messages):
                    fail(f"unexpected messages response: {messages}")
                verify_trace(e2e, messages, approval_id, target, str(fixture))
                verify_messages(e2e, messages, approval_message, approval_id, target)
                verify_artifacts(e2e, fixture, original_snapshot, approval_id, target)
                e2e.emit_timing_summary("analyst-replanning", base_url, session_id, started, checkpoints)
                timing_emitted = True
            except Exception as error:
                if session_id is not None and not timing_emitted:
                    e2e.emit_timing_summary("analyst-replanning", base_url, session_id, started, checkpoints)
                log_file.flush()
                log = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                raise AssertionError(f"{error}\nserver log:\n{log}") from error
            finally:
                cleanup_error = None
                if session_id is not None and process.poll() is None:
                    try:
                        e2e.request_json(base_url, "DELETE", f"/session/{session_id}")
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
                    raise RuntimeError(f"failed to delete analyst replanning E2E session: {cleanup_error}") from cleanup_error


if __name__ == "__main__":
    run()
    print("Analyst replanning E2E passed")
