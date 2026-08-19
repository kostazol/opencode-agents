#!/usr/bin/env python3

import re

from harness import SystemWorkspace
from fixture_validation import parse_question_state


with SystemWorkspace(expected_request="configurable-output-format") as system:
    messages = system.run_transition("Подготовь план добавления configurable output format в `1_orchestrator/configurable-output-format/`. Формат существенно влияет на API, но пользователь ещё не выбрал JSON или plain text. Исследуй repository и сохрани вопросы.")
    targets = list((system.workspace / "1_orchestrator").glob("*/questions.md"))
    assert len(targets) == 1, (targets, messages)
    content = targets[0].read_text(encoding="utf-8")
    questions = parse_question_state(targets[0])
    assert questions.status == "pending" and questions.revision >= 1, questions
    assert "recommend" in content.casefold() or "рекоменд" in content.casefold(), content
    assert re.search(r"[А-Яа-яЁё]", content), content
    for english_label in ("Question", "Options", "Recommendation"):
        assert english_label not in content, content
    system.assert_task_sequence(messages, ["orchestrator-discovery"])
print("discovery questions E2E passed")
