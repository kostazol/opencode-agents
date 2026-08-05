#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage


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

Прочитай supplied current stage file. Обнови frontmatter revision с 3 до 4 и сохрани status REVIEW. Верни только:

STAGE_PLAN: REVIEW
STAGE: S01
REVISION: 4
ARTIFACT: 1_orchestrator/e2e/stages/01-value-contract.md
SUMMARY: Finding из review применён.
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

Запиши supplied REVIEW_OUTPUT для stage S01, stage_revision 4, status PASS, без findings и с русским текстом passing checks. Верни только:

STAGE_REVIEW: PASS
STAGE: S01
REVISION: 4
REVIEW: 1_orchestrator/e2e/reviews/01.md
FINDINGS: 0
SUMMARY: План этапа готов к будущей реализации.
"""


system = SystemWorkspace()
try:
    agent_dir = system.workspace / ".opencode/agents"
    (agent_dir / "orchestrator-stage-planner.md").write_text(PLANNER, encoding="utf-8")
    (agent_dir / "orchestrator-stage-reviewer.md").write_text(REVIEWER, encoding="utf-8")
    system.start()
    plan = seed_plan(system.workspace, [("PLANNING", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    stage = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md"
    stage.write_text(stage.read_text(encoding="utf-8").replace("revision: 1", "revision: 3"), encoding="utf-8")
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Revision: 0", "- Revision: 3"), encoding="utf-8")
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    review.write_text("---\nstage: S01\nstage_revision: 3\nstatus: REVISE\n---\n\n# Review S01\n\n## Findings\n- Add deterministic detail.\n", encoding="utf-8")
    messages = system.run_step("RESUME: 1_orchestrator/e2e/plan.md")
    agents = system.task_agents(messages)
    assert agents[-1:] == ["orchestrator-stage-reviewer"], agents
    assert 1 <= agents.count("orchestrator-stage-planner") <= 2, agents
    assert set(agents) == {"orchestrator-stage-planner", "orchestrator-stage-reviewer"}, agents
    content = plan.read_text(encoding="utf-8")
    assert "status: ready" in content, content
    assert "- Status: PASS" in content
    texts = [part.get("text", "") for message in messages for part in message.get("parts", []) if isinstance(part, dict) and part.get("type") == "text"]
    assert any("Итог: READY" in text for text in texts), texts
    assert all("Итог: PAUSED" not in text for text in texts), texts
finally:
    system.close()
print("RUN revise continuation E2E passed")
