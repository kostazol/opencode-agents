#!/usr/bin/env python3

from harness import SystemWorkspace


with SystemWorkspace() as system:
    messages = system.run_transition("Подготовь план добавления configurable output format. Формат существенно влияет на API, но пользователь ещё не выбрал JSON или plain text. Исследуй repository и сохрани вопросы.")
    targets = list((system.workspace / "1_orchestrator").glob("*/questions.md"))
    assert len(targets) == 1, (targets, messages)
    content = targets[0].read_text(encoding="utf-8")
    assert "status: pending" in content
    assert "recommend" in content.casefold() or "рекоменд" in content.casefold(), content
    assert system.task_agents(messages) == ["orchestrator-discovery"]
print("discovery questions E2E passed")
