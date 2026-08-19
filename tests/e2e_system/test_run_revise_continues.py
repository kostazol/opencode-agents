#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, mutate_artifact_frontmatter, mutate_stage_map_entry, parse_plan_frontmatter, parse_stage_map_entry, validate_fixture_state, write_technical_review


PLANNER = """---
description: Deterministic RUN routing planner fixture.
mode: subagent
hidden: true
permission:
  "*": deny
  read: allow
  edit:
    "*": deny
    "1_orchestrator/**": allow
    "*/1_orchestrator/**": allow
---

Если supplied mode TECHNICAL, прочитай current stage file, обнови frontmatter revision с 3 до 4, сохрани status REVIEW и верни только:

STAGE_PLAN: REVIEW
STAGE: S01
REVISION: 4
ARTIFACT: 1_orchestrator/e2e/stages/01-value-contract.md
SUMMARY: Finding из review применён.

Если supplied mode HUMAN_REVIEW, запиши supplied human-review path ровно с этим содержимым:

---
stage: S01
status: REVIEW
revision: 1
source_revision: 4
---

# S01 — Контракт значения

## Что я получу после этапа
Операция возвращает целое число `1`.

## Как это будет выглядеть в работе
1. Потребитель вызывает операцию без входных данных.
2. Операция возвращает `1` без изменения состояния.

## Что именно будет сделано
- Сохранён контракт значения и его автоматическая проверка.

## Чего после этапа ещё не будет
- Дополнительных значений и изменения состояния.

## Что важно подтвердить перед реализацией
Значение `1` уже подтверждено техническим планом.

## Как принять готовую реализацию
- [ ] Возвращается целое число `1`.
- [ ] Состояние не меняется.

## Статус
Технический план проверен. План ожидает `APPROVE PLAN`; реализация ещё не началась.

После записи верни только:

STAGE_PLAN: REVIEW
STAGE: S01
REVISION: 1
ARTIFACT: 1_orchestrator/e2e/stages/01-value-contract.human-review.md
SUMMARY: Человекочитаемый план создан.
"""

REVIEWER = """---
description: Deterministic RUN routing reviewer fixture.
mode: subagent
hidden: true
permission:
  "*": deny
  read: allow
  edit:
    "*": deny
    "1_orchestrator/**": allow
    "*/1_orchestrator/**": allow
---

Если supplied mode TECHNICAL, запиши supplied REVIEW_OUTPUT для stage S01, stage_revision 4, status PASS, без findings и с русским текстом passing checks. Верни только:

STAGE_REVIEW: PASS
STAGE: S01
REVISION: 4
REVIEW: 1_orchestrator/e2e/reviews/01.md
FINDINGS: 0
SUMMARY: План этапа готов к будущей реализации.

Если supplied mode HUMAN_REVIEW, запиши supplied REVIEW_OUTPUT ровно с этим содержимым:

---
stage: S01
stage_revision: 1
source_revision: 4
status: PASS
---

# Review S01

## Findings
- Нет.

## Checks
- Соответствие техническому плану: PASS
- Итог этапа и практическая работа: PASS
- Сценарии, ошибки и изменения состояния: PASS
- Границы, риски и вопросы для подтверждения: PASS
- Понятность без глубоких технических знаний: PASS

После записи верни только:

STAGE_REVIEW: PASS
STAGE: S01
REVISION: 1
REVIEW: 1_orchestrator/e2e/reviews/01-human-review.md
FINDINGS: 0
SUMMARY: Человекочитаемый план верно передаёт технический план.
"""


system = SystemWorkspace()
try:
    agent_dir = system.workspace / ".opencode/agents"
    (agent_dir / "orchestrator-stage-planner.md").write_text(PLANNER, encoding="utf-8")
    (agent_dir / "orchestrator-stage-reviewer.md").write_text(REVIEWER, encoding="utf-8")
    plan = seed_plan(system.workspace, [("PLANNING", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    stage = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md"
    mutate_artifact_frontmatter(stage, revision=3)
    mutate_stage_map_entry(plan, "S01", revision=3)
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    write_technical_review(review, "S01", 3, "REVISE", "Add deterministic detail.")
    validate_fixture_state(plan, "S01", stage, review, expected_plan=PlanFrontmatter("planning", "S01"), expected_stage_status="PLANNING", expected_artifact_status="REVIEW", expected_review_status="REVISE")
    system.start()
    messages = system.run_step("RESUME: 1_orchestrator/e2e/plan.md")
    system.assert_task_sequence(messages, ["orchestrator-stage-planner", "orchestrator-stage-reviewer", "orchestrator-stage-planner", "orchestrator-stage-reviewer"])
    assert parse_plan_frontmatter(plan) == PlanFrontmatter("waiting-plan-approval", "none")
    assert parse_stage_map_entry(plan, "S01").status == "PASS"
    texts = [part.get("text", "") for message in messages for part in message.get("parts", []) if isinstance(part, dict) and part.get("type") == "text"]
    assert any("Итог: WAITING_INPUT" in text for text in texts), texts
    assert all("Итог: PAUSED" not in text for text in texts), texts
finally:
    system.close()
print("RUN revise continuation E2E passed")
