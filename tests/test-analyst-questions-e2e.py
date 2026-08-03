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
PROMPT = """Подготовь план, не реализуй. Это CREATE: используй Target `1_orchestrator/analyst-e2e-questions`, Lineage ID `analyst-e2e-questions`, Generation `0`, Approval ID `analyst-e2e-questions-g0`; существующий target не предоставлен, completed task paths — none.
Задача: спланировать экспорт audit events. До пользовательских решений INITIAL должен содержать ровно два provisional этапа: S01 export generation и S02 delivery/rollout integration. Материально не определены ровно три решения; никакие repository evidence или defaults их не закрывают. Вызови native OpenCode `question` ровно один раз с тремя отдельными карточками и без других вопросов:
1. Header `Доставка`: варианты с точными labels `Download` и `Object storage`.
2. Header `Формат`: варианты с точными labels `CSV` и `JSONL`.
3. Header `Запуск`: варианты с точными labels `Immediate` и `Feature flag`.
Не выбирай ответы сам. После ответов полностью перегенерируй RESTAGE. Если выбраны `Object storage`, `JSONL`, `Feature flag`, RESTAGE должен добавить один этап и содержать ровно три этапа с полностью заданными контрактами:
S01 JSONL export generation — только `src/export.py`, `tests/test_export.py`; `build_jsonl(events: list[dict[str, str]]) -> bytes` сохраняет input order, кодирует каждую запись через `json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, разделяет записи `\n`, добавляет final `\n` только для непустого input, возвращает UTF-8 bytes, для пустого input возвращает `b""`; unittest проверяет exact bytes, Unicode, input order, sorted keys и empty input.
S02 object-storage delivery — только `src/storage.py`, `tests/test_storage.py`; `store_export(artifact: bytes, upload: Callable[[str, bytes], None]) -> str` вызывает `upload("audit/events.jsonl", artifact)` ровно один раз, возвращает exact key `audit/events.jsonl`, без изменения propagates тот же exception object; unittest mock проверяет exact call, key, return и exception identity. S02 execution prerequisite — S01 COMPLETE/PASS; входной artifact contract — exact bytes из S01.
S03 feature-flag rollout/integration — только `src/rollout.py`, `tests/test_rollout.py`; `export_if_enabled(enabled: bool, events: list[dict[str, str]], upload: Callable[[str, bytes], None]) -> str | None`; false возвращает None без вызовов S01/S02, true ровно один раз вызывает S01 `build_jsonl`, передаёт exact bytes в S02 `store_export` и возвращает его key; exceptions propagate unchanged. Unittest mock проверяет disabled path, exact enabled S01→S02 handoff, return и exception identity. S03 execution prerequisite — S02 COMPLETE/PASS.
Порядок строго S01, S02, S03. Контракты между этапами должны быть явными; caller/registration paths отсутствуют и не нужны. После stage reviews проверь пары S01+S02 и S02+S03. Только Python standard library. Не менять существующие product files, конфигурацию, зависимости или Git. После approval создай ровно три task files, добейся PASS каждого stage, проверь обе пары и FINALIZE до READY. Executor не запускай."""
EXPECTED_ANSWERS = {
    "Доставка": "Object storage",
    "Формат": "JSONL",
    "Запуск": "Feature flag",
}
EXPECTED_OPTIONS = {
    "Доставка": ["Download", "Object storage"],
    "Формат": ["CSV", "JSONL"],
    "Запуск": ["Immediate", "Feature flag"],
}
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


def wait_for_question(e2e: ModuleType, base_url: str, session_id: str, process: subprocess.Popen[str], log_path: Path) -> dict[str, Any]:
    deadline = time.monotonic() + e2e.TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            fail(f"opencode serve exited with {process.returncode}:\n{log_path.read_text(encoding='utf-8', errors='replace')[-4000:]}")
        pending = e2e.request_json(base_url, "GET", "/question")
        if isinstance(pending, list):
            owned = [request for request in pending if isinstance(request, dict) and request.get("sessionID") == session_id]
            if len(owned) == 1:
                return owned[0]
            if len(owned) > 1:
                fail(f"expected one native question request, got {owned}")
        time.sleep(2)
    fail("native question request did not appear")


def wait_for_approval(e2e: ModuleType, base_url: str, session_id: str, process: subprocess.Popen[str], log_path: Path) -> tuple[list[dict[str, Any]], str]:
    deadline = time.monotonic() + e2e.TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            fail(f"opencode serve exited with {process.returncode}:\n{log_path.read_text(encoding='utf-8', errors='replace')[-4000:]}")
        messages = e2e.request_json(base_url, "GET", f"/session/{session_id}/message")
        if isinstance(messages, list):
            typed = [message for message in messages if isinstance(message, dict)]
            texts = ["\n".join(e2e.text_parts(message)) for message in typed if isinstance(message.get("info"), dict) and message["info"].get("role") == "assistant" and e2e.text_parts(message)]
            approval_texts = [text for text in texts if "Итог: НУЖНО_ОДОБРЕНИЕ" in text]
            if len(approval_texts) == 1:
                return typed, approval_texts[0]
        time.sleep(3)
    fail("analyst did not produce approval proposal after question reply")


def verify_question(request: dict[str, Any]) -> list[list[str]]:
    request_id = request.get("id")
    questions = request.get("questions")
    if not isinstance(request_id, str) or not request_id.startswith("que") or not isinstance(questions, list) or len(questions) != 3:
        fail(f"invalid native question request: {request}")
    by_header = {}
    for question in questions:
        if not isinstance(question, dict) or not isinstance(question.get("header"), str) or not isinstance(question.get("question"), str):
            fail(f"invalid question card: {question}")
        header = question["header"]
        if header in by_header:
            fail(f"duplicate question header: {header}")
        options = question.get("options")
        if not isinstance(options, list):
            fail(f"question lacks options: {question}")
        labels = [option.get("label") for option in options if isinstance(option, dict)]
        expected = EXPECTED_ANSWERS.get(header)
        expected_options = EXPECTED_OPTIONS.get(header)
        if expected is None or labels != expected_options:
            fail(f"question {header} has wrong options: {labels}, expected {expected_options}")
        by_header[header] = expected
    if set(by_header) != set(EXPECTED_ANSWERS):
        fail(f"unexpected question headers: {sorted(by_header)}")
    return [[by_header[question["header"]]] for question in questions]


def accepted_task_calls(e2e: ModuleType, messages: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
    calls = [e2e.completed_task_output(part) for part in e2e.task_parts(messages)]
    rejected_statuses = {f"{contract}: {status}" for contract in ("STAGE_DECOMPOSITION", "QUESTION_REVIEW", "PLANNING", "STAGE_REVIEW", "PAIR_REVIEW") for status in ("REJECTED", "BLOCKED")}
    rejected = [(subagent, prompt, output) for subagent, prompt, output in calls if rejected_statuses.intersection(line.strip() for line in output.splitlines())]
    if len(rejected) > 3:
        fail(f"too many malformed-input retries: {len(rejected)}")
    for _, _, output in rejected:
        rejection_reasons = [reason for reason in e2e.field_values(output, "Rejection") if reason.strip() != "none"]
        blocker_reasons = [reason for reason in e2e.field_values(output, "Блокер") if reason.strip() != "none"]
        if len(rejection_reasons) + len(blocker_reasons) != 1:
            fail(f"malformed retry lacks one reason:\n{output}")
    accepted = [call for call in calls if call not in rejected]
    restage_indices = [index for index, (subagent, _, output) in enumerate(accepted) if subagent == "orchestrator-stage-decomposer" and e2e.field_values(output, "MODE") == ["RESTAGE"]]
    if len(restage_indices) not in (1, 2):
        fail(f"expected one RESTAGE or one bounded regeneration, got {restage_indices}")
    if len(restage_indices) == 2:
        if restage_indices != [2, 3]:
            fail(f"RESTAGE regeneration occurred out of order: {restage_indices}")
        del accepted[2]
    subagents = [subagent for subagent, _, _ in accepted]
    prompts = [prompt for _, prompt, _ in accepted]
    outputs = [output for _, _, output in accepted]
    if any(subagent not in e2e.ANALYST_SUBAGENTS for subagent in subagents):
        fail(f"unexpected or executor subagent invoked: {subagents}")
    return subagents, prompts, outputs


def verify_planning(e2e: ModuleType, messages: list[dict[str, Any]], approval_id: str, target: str, workflow_base: str) -> dict[str, int]:
    _, prompts, outputs = accepted_task_calls(e2e, messages)
    e2e.require_fields(outputs[0], {"STAGE_DECOMPOSITION": "PASS", "MODE": "INITIAL", "Stage count": "2", "Origin": "CREATE", "Rejection": "none"})
    e2e.require_fields(outputs[1], {"QUESTION_REVIEW": "QUESTIONS", "Origin": "CREATE", "Rejection": "none"})
    e2e.require_fields(outputs[2], {"STAGE_DECOMPOSITION": "PASS", "MODE": "RESTAGE", "Stage count": "3", "Origin": "CREATE", "Approval ID": approval_id, "Rejection": "none"})
    final_revisions = {}
    for stage_id in ("S01", "S02", "S03"):
        planned = [output for output in outputs if e2e.field_values(output, "PLANNING") == ["PASS"] and e2e.field_values(output, "MODE") == ["PLAN_STAGE"] and e2e.field_values(output, "Stage ID") == [stage_id]]
        reviews = [output for output in outputs if e2e.field_values(output, "STAGE_REVIEW") and e2e.field_values(output, "Stage ID") == [stage_id]]
        if len(planned) != 1 or not reviews or e2e.field_values(reviews[-1], "STAGE_REVIEW") != ["PASS"]:
            fail(f"stage {stage_id} lacks initial planning or final PASS")
        revision = e2e.single_field(reviews[-1], "Stage revision")
        if not revision.isdigit() or int(revision) < 1:
            fail(f"stage {stage_id} has invalid final revision {revision}")
        final_revisions[stage_id] = int(revision)
    for pair_id, left, right in (("S01+S02", "S01", "S02"), ("S02+S03", "S02", "S03")):
        reviews = [output for output in outputs if e2e.field_values(output, "PAIR_REVIEW") and e2e.field_values(output, "Pair ID") == [pair_id]]
        if not reviews or e2e.field_values(reviews[-1], "PAIR_REVIEW") != ["PASS"]:
            fail(f"pair {pair_id} lacks PASS")
        if e2e.single_field(reviews[-1], "Left stage") != f"{left} revision {final_revisions[left]}" or e2e.single_field(reviews[-1], "Right stage") != f"{right} revision {final_revisions[right]}":
            fail(f"pair {pair_id} PASS is stale")
    finalizations = [output for output in outputs if e2e.field_values(output, "PLANNING") == ["PASS"] and e2e.field_values(output, "MODE") == ["FINALIZE"]]
    if len(finalizations) != 1 or outputs[-1] != finalizations[0]:
        fail(f"workflow lacks one final FINALIZE PASS:\n{outputs[-1]}")
    for index, output in enumerate(outputs):
        if e2e.single_field(output, "Lineage ID") != "analyst-e2e-questions" or e2e.single_field(output, "Generation") != "0" or e2e.single_field(output, "Origin") != "CREATE" or e2e.single_field(output, "Target") != target:
            fail("inconsistent workflow identity in task output")
        if index >= 3 and (e2e.single_field(output, "Approval ID") != approval_id or e2e.single_field(output, "Effective-contract ID") != approval_id):
            fail("post-approval task output has inconsistent contract identity")
    if len(prompts) != len(outputs):
        fail("task prompt/output count mismatch")
    restage_section = outputs[2].split("Stages:", 1)
    if len(restage_section) != 2:
        fail("RESTAGE lacks stage section")
    stage_text = restage_section[1].split("Question-review input:", 1)[0]
    stage_positions = [stage_text.find(stage_id) for stage_id in ("S01", "S02", "S03")]
    if stage_positions[0] < 0 or not stage_positions[0] < stage_positions[1] < stage_positions[2]:
        fail("RESTAGE stage order is not S01, S02, S03")
    segments = [stage_text[stage_positions[0]:stage_positions[1]].lower().replace("-", " "), stage_text[stage_positions[1]:stage_positions[2]].lower().replace("-", " "), stage_text[stage_positions[2]:].lower().replace("-", " ")]
    required_segments = (
        ("jsonl", "src/export.py", "tests/test_export.py", "contracts:"),
        ("object storage", "src/storage.py", "tests/test_storage.py", "s01", "complete/pass", "contracts:"),
        ("feature flag", "src/rollout.py", "tests/test_rollout.py", "s02", "complete/pass", "contracts:"),
    )
    for stage_id, segment, required_values in zip(("S01", "S02", "S03"), segments, required_segments):
        for required in required_values:
            if required not in segment:
                fail(f"RESTAGE {stage_id} lacks {required}")
    return final_revisions


def verify_messages(e2e: ModuleType, messages: list[dict[str, Any]], approval_id: str, target: str, approval_message: str, final_revisions: dict[str, int]) -> None:
    user_messages = [message for message in messages if isinstance(message.get("info"), dict) and message["info"].get("role") == "user"]
    if ["\n".join(e2e.text_parts(message)) for message in user_messages] != [PROMPT, approval_message]:
        fail("question answers were not carried exclusively by native question API")
    question_parts = [part for message in messages for part in message.get("parts", []) if isinstance(part, dict) and part.get("type") == "tool" and part.get("tool") == "question"]
    if len(question_parts) != 1 or not isinstance(question_parts[0].get("state"), dict) or question_parts[0]["state"].get("status") != "completed":
        fail(f"expected one completed native question tool call, got {question_parts}")
    assistant_texts = ["\n".join(e2e.text_parts(message)) for message in messages if isinstance(message.get("info"), dict) and message["info"].get("role") == "assistant" and e2e.text_parts(message)]
    approval = [text for text in assistant_texts if "Итог: НУЖНО_ОДОБРЕНИЕ" in text]
    ready = [text for text in assistant_texts if "Итог: READY" in text]
    if len(approval) != 1 or len(ready) != 1:
        fail(f"expected one approval and one READY response: {assistant_texts}")
    for text in (approval[0], ready[0]):
        if e2e.single_field(text, "Approval ID") != approval_id or e2e.single_field(text, "Target") != target:
            fail("assistant response identity mismatch")
    for answer in EXPECTED_ANSWERS.values():
        if answer not in approval[0]:
            fail(f"approval response omits resolved decision {answer}")
    for required in (*(f"{stage_id} revision {revision} — PASS" for stage_id, revision in final_revisions.items()), "Действие: none"):
        if required not in ready[0]:
            fail(f"READY response lacks {required}")
    if ready[0].count("— PASS") < 3:
        fail("READY response does not report three stage PASS results")


def verify_artifacts(e2e: ModuleType, fixture: Path, original_snapshot: dict[str, tuple[str, int, bytes]], approval_id: str, target: str, final_revisions: dict[str, int]) -> None:
    target_root = fixture / target
    workflow_root = fixture / "1_orchestrator"
    if list(workflow_root.iterdir()) != [target_root]:
        fail(f"expected sole workflow target {target_root}")
    task_files = sorted((target_root / "tasks").glob("*.md"))
    if len(task_files) != 3:
        fail(f"expected three task files, got {task_files}")
    for index, task_file in enumerate(task_files, start=1):
        content = task_file.read_text(encoding="utf-8")
        for required in (f"- Stage ID: S0{index}", f"- Approval ID: {approval_id}", f"- Effective-contract ID: {approval_id}", "- Status: READY", "- Planning review: PASS", "- Result: NOT_STARTED"):
            if required not in content:
                fail(f"{task_file} lacks {required}")
        revision_lines = [line for line in content.splitlines() if line.startswith("- Stage revision: ")]
        expected_revision = final_revisions[f"S0{index}"]
        if revision_lines != [f"- Stage revision: {expected_revision}"]:
            fail(f"{task_file} has stale stage revision: {revision_lines}")
        prerequisite_parts = content.split("## Ordered prerequisites", 1)
        if len(prerequisite_parts) != 2:
            fail(f"{task_file} lacks prerequisite section")
        prerequisite_section = prerequisite_parts[1].split("## ", 1)[0].strip()
        prerequisite_lines = [line.strip() for line in prerequisite_section.splitlines() if line.strip()]
        if index == 1:
            if prerequisite_lines != ["- None"]:
                fail(f"{task_file} must have exact None prerequisite: {prerequisite_lines}")
        else:
            previous = task_files[index - 2].relative_to(fixture)
            if len(prerequisite_lines) != 1 or str(previous) not in prerequisite_lines[0] or "COMPLETE" not in prerequisite_lines[0] or "PASS" not in prerequisite_lines[0]:
                fail(f"{task_file} lacks exact coordinated prerequisite {previous}: {prerequisite_lines}")
    journal = target_root / "planning-issues.md"
    expected_files = {journal, *task_files}
    actual_files = {path for path in target_root.rglob("*") if path.is_file() or path.is_symlink()}
    if actual_files != expected_files:
        fail(f"unexpected workflow artifacts: {sorted(actual_files)}")
    expected_directories = {target_root / "tasks"}
    actual_directories = {path for path in target_root.rglob("*") if path.is_dir()}
    if actual_directories != expected_directories:
        fail(f"unexpected workflow directories: {sorted(actual_directories)}")
    if e2e.workspace_snapshot(fixture) != original_snapshot:
        fail("analyst changed product workspace")


def run() -> None:
    e2e = load_e2e()
    opencode = shutil.which("opencode")
    if opencode is None:
        fail("opencode executable not found")
    with tempfile.TemporaryDirectory(prefix="opencode-analyst-questions-e2e-") as temporary:
        temporary_root = Path(temporary)
        fixture = temporary_root / "fixture"
        fixture.mkdir()
        e2e.write_fixture(fixture)
        original_snapshot = e2e.workspace_snapshot(fixture)
        config_home = temporary_root / "config-home"
        config = config_home / "opencode"
        subprocess.run([sys.executable, str(e2e.CLI), "install", "--source", str(ROOT), "--target", str(config)], check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
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
        environment.update({"HOME": str(isolated_home), "XDG_CONFIG_HOME": str(config_home), "XDG_DATA_HOME": str(data_home), "XDG_STATE_HOME": str(temporary_root / "state-home"), "XDG_CACHE_HOME": str(temporary_root / "cache-home"), "OPENCODE_CONFIG_DIR": str(config), "OPENCODE_DISABLE_CLAUDE_CODE": "1", "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "1", "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1"})
        log_path = temporary_root / "server.log"
        session_id = None
        with log_path.open("w", encoding="utf-8") as log_file:
            process, base_url = e2e.start_server(opencode, fixture, environment, log_file, log_path)
            try:
                session = e2e.request_json(base_url, "POST", "/session", {"title": "Analyst native-question E2E"})
                if not isinstance(session, dict) or not isinstance(session.get("id"), str):
                    fail(f"unexpected session response: {session}")
                session_id = session["id"]
                e2e.request_json(base_url, "POST", f"/session/{session_id}/prompt_async", {"agent": "orchestrator-analyst", "parts": [{"type": "text", "text": PROMPT}]})
                question_request = wait_for_question(e2e, base_url, session_id, process, log_path)
                answers = verify_question(question_request)
                if (fixture / "1_orchestrator").exists():
                    fail("analyst wrote workflow artifacts before question answers")
                reply = e2e.request_json(base_url, "POST", f"/question/{question_request['id']}/reply", {"answers": answers})
                if reply is not True:
                    fail(f"native question reply failed: {reply}")
                _, approval_text = wait_for_approval(e2e, base_url, session_id, process, log_path)
                if (fixture / "1_orchestrator").exists():
                    fail("analyst wrote workflow artifacts before approval")
                approval_id = e2e.single_field(approval_text, "Approval ID")
                target = e2e.single_field(approval_text, "Target")
                if approval_id != "analyst-e2e-questions-g0" or target != "1_orchestrator/analyst-e2e-questions":
                    fail(f"unexpected approval identity: {approval_id}, {target}")
                approval_message = f"APPROVE {approval_id}"
                e2e.request_json(base_url, "POST", f"/session/{session_id}/prompt_async", {"agent": "orchestrator-analyst", "parts": [{"type": "text", "text": approval_message}]})
                e2e.wait_for_idle(base_url, session_id, process, log_path)
                messages = e2e.request_json(base_url, "GET", f"/session/{session_id}/message")
                if not isinstance(messages, list) or not all(isinstance(message, dict) for message in messages):
                    fail(f"unexpected messages response: {messages}")
                final_revisions = verify_planning(e2e, messages, approval_id, target, str(fixture))
                verify_messages(e2e, messages, approval_id, target, approval_message, final_revisions)
                verify_artifacts(e2e, fixture, original_snapshot, approval_id, target, final_revisions)
                pending = e2e.request_json(base_url, "GET", "/question")
                if isinstance(pending, list) and any(isinstance(request, dict) and request.get("sessionID") == session_id for request in pending):
                    fail("native question request remained pending")
            except Exception as error:
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
                    raise RuntimeError(f"failed to delete analyst question E2E session: {cleanup_error}") from cleanup_error


if __name__ == "__main__":
    run()
    print("Analyst question E2E passed")
