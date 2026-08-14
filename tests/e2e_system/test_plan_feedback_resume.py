#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_human_review, write_passed_stage
from fixture_validation import assert_fixture_state, replace_required


DISCOVERY = """---
description: Deterministic plan-feedback discovery fixture.
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

В supplied `PLAN_FEEDBACK` mode обработай latest pending feedback. В `plan.md` сохрани S01 без изменений. Сбрось affected S02 и dependent S03 в `PROPOSED`, установи им technical revision 2, human-review revision 2, human-review status `PENDING`. Установи frontmatter `status: waiting-approval`, `current_stage: none`. В `feedback.md` сохрани историю, отметь Feedback 1 как `applied`, укажи `Affected stages: [S02, S03]`, установи `mode: none`. Верни только:

DISCOVERY: READY_FOR_APPROVAL
ARTIFACT: 1_orchestrator/e2e/discovery.md
QUESTIONS: none
PLAN: 1_orchestrator/e2e/plan.md
SUMMARY: Замечание применено к S02 и S03; S01 сохранён.
"""


system = SystemWorkspace()
try:
    agent = system.workspace / ".opencode/agents/orchestrator-discovery.md"
    agent.write_text(DISCOVERY, encoding="utf-8")
    plan = seed_plan(system.workspace, [("PASS", "Value contract"), ("PASS", "Value consumer"), ("PASS", "Value docs")], "none", "waiting-plan-approval")
    for number, title in enumerate(("Value contract", "Value consumer", "Value docs"), start=1):
        write_passed_stage(system.workspace, number, title)
        write_passed_human_review(system.workspace, number, title)
    replace_required(plan, "- Human review revision: 0", "- Human review revision: 1", expected_count=3)
    replace_required(plan, "- Human review status: PENDING", "- Human review status: PASS", expected_count=3)
    feedback = system.workspace / "1_orchestrator/e2e/feedback.md"
    feedback.write_text("---\nlatest_revision: 1\nmode: PLAN_FEEDBACK\n---\n\n## Feedback 1\nStatus: pending\nRemarks: Значение потребителя должно отображаться как 2.\nAffected stages: unknown\nQuestions: none\n", encoding="utf-8")
    for number, title in enumerate(("value-contract", "value-consumer", "value-docs"), start=1):
        human_review = system.workspace / f"1_orchestrator/e2e/stages/{number:02d}-{title}.human-review.md"
        review = system.workspace / f"1_orchestrator/e2e/reviews/{number:02d}-human-review.md"
        assert_fixture_state(plan, "waiting-plan-approval", "none", f"S{number:02d}", {"Status": "PASS", "Revision": "1", "Human review revision": "1", "Human review status": "PASS"}, human_review, {"revision": "1", "source_revision": "1"}, review, {"stage_revision": "1", "source_revision": "1", "status": "PASS"})
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    feedback_content = feedback.read_text(encoding="utf-8")
    assert "status: waiting-approval" in content, (content, messages)
    assert "### S01" in content and "### S02" in content and "### S03" in content, content
    s01, remainder = content.split("### S02", 1)
    s02, s03 = remainder.split("### S03", 1)
    assert "- Status: PASS" in s01 and "- Revision: 1" in s01 and "- Human review revision: 1" in s01 and "- Human review status: PASS" in s01, s01
    for affected in (s02, s03):
        assert "- Status: PROPOSED" in affected and "- Revision: 2" in affected, affected
        assert "- Human review revision: 2" in affected and "- Human review status: PENDING" in affected, affected
    assert "latest_revision: 1" in feedback_content and "mode: none" in feedback_content, feedback_content
    assert "Status: applied" in feedback_content and "Affected stages: [S02, S03]" in feedback_content, feedback_content
    assert system.task_agents(messages) == ["orchestrator-discovery"]
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md\nAPPROVE")
    content = plan.read_text(encoding="utf-8")
    assert "status: planning" in content and "current_stage: S02" in content, (content, messages)
    assert system.task_agents(messages) == []
finally:
    system.close()
print("plan feedback resume E2E passed")
