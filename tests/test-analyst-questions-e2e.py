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
PROMPT = """Подготовь план, не реализуй. Это CREATE: используй Target `1_orchestrator/questions-e2e`, Lineage ID `questions-e2e`, Generation `0`, Approval ID `questions-e2e-g0`; существующий target не предоставлен, completed task paths — none.
Задача: спланировать экспорт audit events. До пользовательских решений INITIAL должен содержать ровно два provisional этапа: S01 export generation и S02 delivery/rollout integration. INITIAL использует Discovery round `0`, Discovery ID `questions-e2e-d0`. На этом evidence materially unresolved только способ доставки: first question review `questions-e2e-qr0`, batch `questions-e2e-b1`, одна карточка с Header `Доставка` и вариантами с точными labels `Download` и `Object storage`. Не задавай формат или запуск в первом batch.
Не выбирай ответы сам. После ответа `Object storage` выполни fresh DISCOVERY round `1` с ID `questions-e2e-d1`: дополнительно исследуй storage boundary и обнови provisional stages. Только это исследование открывает ещё ровно два material decisions. Fresh review `questions-e2e-qr1`, batch `questions-e2e-b2` должен вызвать второй native question с двумя отдельными карточками и без других вопросов:
1. Header `Формат`: варианты с точными labels `CSV` и `JSONL`.
2. Header `Запуск`: варианты с точными labels `Immediate` и `Feature flag`.
После ответов `JSONL` и `Feature flag` выполни fresh DISCOVERY round `2` с ID `questions-e2e-d2`, затем fresh terminal review `questions-e2e-qr2` с `PASS_NO_QUESTIONS`. Только после него полностью перегенерируй RESTAGE. Не задавай вопросов после RESTAGE. RESTAGE должен добавить один этап и содержать ровно три этапа с полностью заданными контрактами:
S01 JSONL export generation — только `src/export.py`, `tests/test_export.py`; `build_jsonl(events: list[dict[str, str]]) -> bytes` сохраняет input order, кодирует каждую запись через `json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, разделяет записи `\n`, добавляет final `\n` только для непустого input, возвращает UTF-8 bytes, для пустого input возвращает `b""`; unittest проверяет exact bytes, Unicode, input order, sorted keys и empty input.
S02 object-storage delivery — только `src/storage.py`, `tests/test_storage.py`; `store_export(artifact: bytes, upload: Callable[[str, bytes], None]) -> str` вызывает `upload("audit/events.jsonl", artifact)` ровно один раз, возвращает exact key `audit/events.jsonl`, без изменения propagates тот же exception object; unittest mock проверяет exact call, key, return и exception identity. S02 execution prerequisite — S01 COMPLETE/PASS; входной artifact contract — exact bytes из S01.
S03 feature-flag rollout/integration — только `src/rollout.py`, `tests/test_rollout.py`; `export_if_enabled(enabled: bool, events: list[dict[str, str]], upload: Callable[[str, bytes], None]) -> str | None`; false возвращает None без вызовов S01/S02, true ровно один раз вызывает S01 `build_jsonl`, передаёт exact bytes в S02 `store_export` и возвращает его key; exceptions propagate unchanged. Unittest mock проверяет disabled path, exact enabled S01→S02 handoff, return и exception identity. S03 execution prerequisite — S02 COMPLETE/PASS.
Порядок строго S01, S02, S03. Контракты между этапами должны быть явными; caller/registration paths отсутствуют и не нужны. После stage reviews проверь пары S01+S02 и S02+S03. Только Python standard library. Не менять существующие product files, конфигурацию, зависимости или Git. После approval создай ровно три task files, добейся PASS каждого stage, проверь обе пары и FINALIZE до READY. Executor не запускай."""
EXPECTED_BATCHES = (
    {"Доставка": "Object storage"},
    {"Формат": "JSONL", "Запуск": "Feature flag"},
)
EXPECTED_OPTIONS = {
    "Доставка": ["Download", "Object storage"],
    "Формат": ["CSV", "JSONL"],
    "Запуск": ["Immediate", "Feature flag"],
}
def fail(message: str) -> NoReturn:
    raise AssertionError(message)


def casefold_field(text: str, field: str) -> str:
    prefix = f"{field}: ".casefold()
    values = [line.strip()[len(prefix):] for line in text.splitlines() if line.strip().casefold().startswith(prefix)]
    if len(values) != 1:
        fail(f"expected one case-insensitive {field} field, got {values}")
    return values[0]


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


def verify_question(request: dict[str, Any], expected_answers: dict[str, str]) -> list[list[str]]:
    request_id = request.get("id")
    questions = request.get("questions")
    if not isinstance(request_id, str) or not request_id.startswith("que") or not isinstance(questions, list) or len(questions) != len(expected_answers):
        fail(f"invalid native question request: {request}")
    by_header = {}
    for question in questions:
        if not isinstance(question, dict) or not isinstance(question.get("header"), str) or not isinstance(question.get("question"), str):
            fail(f"invalid question card: {question}")
        header = question["header"]
        if header in by_header:
            fail(f"duplicate question header: {header}")
        options = question.get("options")
        if not isinstance(options, list) or not all(isinstance(option, dict) for option in options):
            fail(f"question lacks options: {question}")
        labels = [option.get("label") for option in options]
        descriptions = [option.get("description") for option in options]
        if any(not isinstance(description, str) or not description.strip() for description in descriptions):
            fail(f"question option lacks consequence description: {question}")
        normalized_labels = [label.removesuffix(" (Recommended)") if isinstance(label, str) else label for label in labels]
        expected = expected_answers.get(header)
        expected_options = EXPECTED_OPTIONS.get(header)
        if expected is None or normalized_labels != expected_options:
            fail(f"question {header} has wrong options: {labels}, expected {expected_options}")
        selected = [label for label, normalized in zip(labels, normalized_labels) if normalized == expected]
        if len(selected) != 1 or not isinstance(selected[0], str):
            fail(f"question {header} lacks one selectable expected answer: {labels}")
        by_header[header] = selected[0]
    if set(by_header) != set(expected_answers):
        fail(f"unexpected question headers: {sorted(by_header)}")
    return [[by_header[question["header"]]] for question in questions]


def accepted_task_calls(e2e: ModuleType, messages: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
    calls = [e2e.completed_task_output(part) for part in e2e.task_parts(messages)]
    rejected_statuses = {f"{contract}: REJECTED" for contract in ("STAGE_DECOMPOSITION", "QUESTION_REVIEW", "PLANNING", "STAGE_REVIEW", "PAIR_REVIEW")}
    substantive_blocked = [output for _, _, output in calls if any(line.strip().endswith(": BLOCKED") for line in output.splitlines()) and not e2e.retryable_blocked_output(output)]
    if substantive_blocked:
        fail(f"substantive BLOCKED output cannot be retried:\n{substantive_blocked[0]}")
    rejected = [(subagent, prompt, output) for subagent, prompt, output in calls if rejected_statuses.intersection(line.strip() for line in output.splitlines()) or e2e.retryable_blocked_output(output) or e2e.malformed_contract_output(output) or e2e.ambiguous_contract_output(subagent, output)]
    if len(rejected) > 3:
        details = "\n--- MALFORMED ---\n".join(f"{subagent}\n{output}" for subagent, _, output in rejected)
        fail(f"too many malformed-input retries: {len(rejected)}\n{details}")
    for subagent, _, output in rejected:
        rejection_reasons = [reason for reason in e2e.field_values(output, "Rejection") if reason.strip() != "none"]
        blocker_reasons = [reason for reason in e2e.field_values(output, "Блокер") if reason.strip() != "none"]
        if not e2e.malformed_contract_output(output) and not e2e.ambiguous_contract_output(subagent, output) and len(rejection_reasons) + len(blocker_reasons) != 1:
            fail(f"malformed retry lacks one reason:\n{output}")
    accepted = [call for call in calls if call not in rejected]
    accepted_restages = [index for index, (subagent, _, output) in enumerate(accepted) if subagent == "orchestrator-stage-decomposer" and e2e.field_values(output, "MODE") == ["RESTAGE"]]
    if len(accepted_restages) != 1:
        fail(f"expected exactly one accepted RESTAGE, got {accepted_restages}")
    first_restage = accepted_restages[0]
    if any(subagent == "orchestrator-stage-question-reviewer" or (subagent == "orchestrator-stage-decomposer" and e2e.field_values(output, "MODE") == ["DISCOVERY"]) for subagent, _, output in accepted[first_restage + 1:]):
        fail("discovery or question review occurred after accepted RESTAGE")
    canonical = []
    for call in accepted:
        if canonical and e2e.task_phase(call[0], call[2]) == e2e.task_phase(canonical[-1][0], canonical[-1][2]):
            canonical[-1] = call
        else:
            canonical.append(call)
    accepted = canonical
    restage_indices = [index for index, (subagent, _, output) in enumerate(accepted) if subagent == "orchestrator-stage-decomposer" and e2e.field_values(output, "MODE") == ["RESTAGE"]]
    if len(restage_indices) != 1:
        fail(f"expected one accepted RESTAGE, got {restage_indices}")
    subagents = [subagent for subagent, _, _ in accepted]
    prompts = [prompt for _, prompt, _ in accepted]
    outputs = [output for _, _, output in accepted]
    if any(subagent not in e2e.ANALYST_SUBAGENTS for subagent in subagents):
        fail(f"unexpected or executor subagent invoked: {subagents}")
    return subagents, prompts, outputs


def verify_planning(e2e: ModuleType, messages: list[dict[str, Any]], approval_id: str, target: str, workflow_base: str) -> dict[str, int]:
    subagents, prompts, outputs = accepted_task_calls(e2e, messages)
    expected_discovery_sequence = ["orchestrator-stage-decomposer", "orchestrator-stage-question-reviewer", "orchestrator-stage-decomposer", "orchestrator-stage-question-reviewer", "orchestrator-stage-decomposer", "orchestrator-stage-question-reviewer", "orchestrator-stage-decomposer"]
    if subagents[:7] != expected_discovery_sequence or any(subagent in ("orchestrator-stage-decomposer", "orchestrator-stage-question-reviewer") for subagent in subagents[7:]):
        fail(f"unexpected discovery sequence or post-RESTAGE discovery: {subagents}")
    e2e.require_fields(outputs[0], {"STAGE_DECOMPOSITION": "PASS", "MODE": "INITIAL", "Discovery round": "0", "Discovery ID": "questions-e2e-d0", "Parent discovery ID": "none", "Stage count": "2", "Origin": "CREATE", "Rejection": "none"})
    e2e.require_fields(outputs[1], {"QUESTION_REVIEW": "QUESTIONS", "Reviewed discovery round": "0", "Reviewed discovery ID": "questions-e2e-d0", "Question-review ID": "questions-e2e-qr0", "Question batch ID": "questions-e2e-b1", "Origin": "CREATE", "Rejection": "none"})
    e2e.require_fields(outputs[2], {"STAGE_DECOMPOSITION": "PASS", "MODE": "DISCOVERY", "Discovery round": "1", "Discovery ID": "questions-e2e-d1", "Question batch ID": "questions-e2e-b1", "Origin": "CREATE", "Approval ID": "none", "Rejection": "none"})
    e2e.require_fields(outputs[3], {"QUESTION_REVIEW": "QUESTIONS", "Reviewed discovery round": "1", "Reviewed discovery ID": "questions-e2e-d1", "Question-review ID": "questions-e2e-qr1", "Question batch ID": "questions-e2e-b2", "Origin": "CREATE", "Rejection": "none"})
    e2e.require_fields(outputs[4], {"STAGE_DECOMPOSITION": "PASS", "MODE": "DISCOVERY", "Discovery round": "2", "Discovery ID": "questions-e2e-d2", "Question batch ID": "questions-e2e-b2", "Origin": "CREATE", "Approval ID": "none", "Rejection": "none"})
    e2e.require_fields(outputs[5], {"QUESTION_REVIEW": "PASS_NO_QUESTIONS", "Reviewed discovery round": "2", "Reviewed discovery ID": "questions-e2e-d2", "Question-review ID": "questions-e2e-qr2", "Question batch ID": "none", "Origin": "CREATE", "Rejection": "none"})
    e2e.require_fields(outputs[6], {"STAGE_DECOMPOSITION": "PASS", "MODE": "RESTAGE", "Discovery round": "2", "Discovery ID": "questions-e2e-d2", "Terminal question-review ID": "questions-e2e-qr2", "Stage count": "3", "Origin": "CREATE", "Approval ID": approval_id, "Rejection": "none"})
    if casefold_field(outputs[2], "Parent discovery ID") != "questions-e2e-d0" or casefold_field(outputs[4], "Parent discovery ID") != "questions-e2e-d1":
        fail("discovery parent linkage is stale")
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
        if e2e.single_field(output, "Lineage ID") != "questions-e2e" or e2e.single_field(output, "Generation") != "0" or e2e.single_field(output, "Origin") != "CREATE" or e2e.single_field(output, "Target") != target:
            fail("inconsistent workflow identity in task output")
        if index >= 7 and (e2e.single_field(output, "Approval ID") != approval_id or e2e.single_field(output, "Effective-contract ID") != approval_id):
            fail("post-approval task output has inconsistent contract identity")
    if len(prompts) != len(outputs):
        fail("task prompt/output count mismatch")
    for index, prompt in enumerate(prompts):
        if not e2e.has_labeled_value(prompt, "WORKFLOW_BASE", workflow_base) or not e2e.has_labeled_value(prompt, "Lineage ID", "questions-e2e") or not e2e.has_labeled_value(prompt, "Generation", "0") or not e2e.has_labeled_value(prompt, "Origin", "CREATE"):
            fail(f"task prompt {index} lacks workflow identity")
    for required in ("questions-e2e-d0", "questions-e2e-qr0", "questions-e2e-b1", "Object storage"):
        if required not in prompts[2]:
            fail(f"first discovery prompt omits first-round value {required}")
    for required in ("questions-e2e-d1", "questions-e2e-d2", "Object storage", "JSONL", "Feature flag"):
        if required not in prompts[5]:
            fail(f"terminal question review prompt omits chain value {required}")
    for required in ("questions-e2e-d2", "questions-e2e-qr2", "PASS_NO_QUESTIONS", "Object storage", "JSONL", "Feature flag"):
        if required not in prompts[6]:
            fail(f"RESTAGE prompt omits terminal chain value {required}")
    restage_section = outputs[6].split("Stages:", 1)
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
    if len(question_parts) != 2 or any(not isinstance(part.get("state"), dict) or part["state"].get("status") != "completed" for part in question_parts):
        fail(f"expected two completed native question tool calls, got {question_parts}")
    tool_parts = [part for message in messages for part in message.get("parts", []) if isinstance(part, dict) and part.get("type") == "tool"]
    restage_positions = [index for index, part in enumerate(tool_parts) if part.get("tool") == "task" and e2e.field_values(e2e.completed_task_output(part)[2], "MODE") == ["RESTAGE"]]
    question_positions = [index for index, part in enumerate(tool_parts) if part.get("tool") == "question"]
    if len(restage_positions) != 1 or not question_positions or max(question_positions) >= min(restage_positions):
        fail("native question occurred after RESTAGE")
    pre_restage_order = []
    for part in tool_parts[:restage_positions[0]]:
        if part.get("tool") == "question":
            pre_restage_order.append("question")
        elif part.get("tool") == "task":
            _, _, output = e2e.completed_task_output(part)
            mode = e2e.field_values(output, "MODE")
            review = e2e.field_values(output, "QUESTION_REVIEW")
            pre_restage_order.append(f"task:{mode[0]}" if mode else f"review:{review[0]}" if review else "task:other")
    expected_order = ["task:INITIAL", "review:QUESTIONS", "question", "task:DISCOVERY", "review:QUESTIONS", "question", "task:DISCOVERY", "review:PASS_NO_QUESTIONS"]
    if pre_restage_order != expected_order:
        fail(f"question/discovery tool order mismatch: {pre_restage_order}")
    assistant_texts = ["\n".join(e2e.text_parts(message)) for message in messages if isinstance(message.get("info"), dict) and message["info"].get("role") == "assistant" and e2e.text_parts(message)]
    approval = [text for text in assistant_texts if "Итог: НУЖНО_ОДОБРЕНИЕ" in text]
    ready = [text for text in assistant_texts if "Итог: READY" in text]
    if len(approval) != 1 or len(ready) != 1:
        fail(f"expected one approval and one READY response: {assistant_texts}")
    for text in (approval[0], ready[0]):
        if e2e.single_field(text, "Approval ID") != approval_id or e2e.single_field(text, "Target") != target:
            fail("assistant response identity mismatch")
    for answer in (answer for batch in EXPECTED_BATCHES for answer in batch.values()):
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
        environment.update({"HOME": str(isolated_home), "XDG_CONFIG_HOME": str(config_home), "XDG_DATA_HOME": str(data_home), "XDG_STATE_HOME": str(temporary_root / "state-home"), "XDG_CACHE_HOME": str(temporary_root / "cache-home"), "OPENCODE_CONFIG_DIR": str(config), "OPENCODE_DISABLE_CLAUDE_CODE": "1", "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "1", "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1", "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1", "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1"})
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
                first_question = wait_for_question(e2e, base_url, session_id, process, log_path)
                first_answers = verify_question(first_question, EXPECTED_BATCHES[0])
                if (fixture / "1_orchestrator").exists():
                    fail("analyst wrote workflow artifacts before question answers")
                first_reply = e2e.request_json(base_url, "POST", f"/question/{first_question['id']}/reply", {"answers": first_answers})
                if first_reply is not True:
                    fail(f"first native question reply failed: {first_reply}")
                second_question = wait_for_question(e2e, base_url, session_id, process, log_path)
                if second_question.get("id") == first_question.get("id"):
                    fail("second question reused first request ID")
                second_answers = verify_question(second_question, EXPECTED_BATCHES[1])
                if (fixture / "1_orchestrator").exists():
                    fail("analyst wrote workflow artifacts before second question answers")
                second_reply = e2e.request_json(base_url, "POST", f"/question/{second_question['id']}/reply", {"answers": second_answers})
                if second_reply is not True:
                    fail(f"second native question reply failed: {second_reply}")
                _, approval_text = wait_for_approval(e2e, base_url, session_id, process, log_path)
                if (fixture / "1_orchestrator").exists():
                    fail("analyst wrote workflow artifacts before approval")
                approval_id = e2e.single_field(approval_text, "Approval ID")
                target = e2e.single_field(approval_text, "Target")
                if approval_id != "questions-e2e-g0" or target != "1_orchestrator/questions-e2e":
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
