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

Read the supplied current stage file. Update its frontmatter revision from 3 to 4 and keep status REVIEW. Return only:

STAGE_PLAN: REVIEW
STAGE: S01
REVISION: 4
ARTIFACT: 1_orchestrator/e2e/stages/01-value-contract.md
SUMMARY: Applied review finding.
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

Write the supplied REVIEW_OUTPUT with stage S01, stage_revision 4, status PASS, no findings, and passing checks. Return only:

STAGE_REVIEW: PASS
STAGE: S01
REVISION: 4
REVIEW: 1_orchestrator/e2e/reviews/01.md
FINDINGS: 0
SUMMARY: Stage ready.
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
    messages = system.run_step("MODE: RUN\nRESUME: 1_orchestrator/e2e/plan.md")
    assert system.task_agents(messages) == ["orchestrator-stage-planner", "orchestrator-stage-reviewer"], system.task_agents(messages)
    content = plan.read_text(encoding="utf-8")
    assert "status: ready" in content, content
    assert "- Status: PASS" in content
    texts = [part.get("text", "") for message in messages for part in message.get("parts", []) if isinstance(part, dict) and part.get("type") == "text"]
    assert any("Итог: READY" in text for text in texts), texts
    assert all("Итог: PAUSED" not in text for text in texts), texts
finally:
    system.close()
print("RUN revise continuation E2E passed")
