#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_human_review, write_passed_stage
from fixture_validation import FeedbackEntry, PlanFrontmatter, mutate_plan_frontmatter, mutate_stage_map_entry, parse_feedback_state, parse_plan_frontmatter, parse_stage_map_entry, validate_fixture_state, write_feedback_state


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
    for stage_id in ("S01", "S02", "S03"):
        mutate_stage_map_entry(plan, stage_id, human_review_revision=1, human_review_status="PASS")
    feedback = system.workspace / "1_orchestrator/e2e/feedback.md"
    write_feedback_state(feedback, 1, "PLAN_FEEDBACK", (FeedbackEntry(1, "pending", "Значение потребителя должно отображаться как 2.", None, "none"),))
    mutate_plan_frontmatter(plan, status="discovery")
    for number, title in enumerate(("value-contract", "value-consumer", "value-docs"), start=1):
        validate_fixture_state(plan, f"S{number:02d}", system.workspace / f"1_orchestrator/e2e/stages/{number:02d}-{title}.md", system.workspace / f"1_orchestrator/e2e/reviews/{number:02d}.md", expected_plan=PlanFrontmatter("discovery", "none"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS")
        validate_fixture_state(plan, f"S{number:02d}", system.workspace / f"1_orchestrator/e2e/stages/{number:02d}-{title}.human-review.md", system.workspace / f"1_orchestrator/e2e/reviews/{number:02d}-human-review.md", human=True, expected_plan=PlanFrontmatter("discovery", "none"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS")
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    assert parse_plan_frontmatter(plan) == PlanFrontmatter("waiting-approval", "none")
    s01 = parse_stage_map_entry(plan, "S01")
    assert (s01.status, s01.revision, s01.human_review_revision, s01.human_review_status) == ("PASS", 1, 1, "PASS"), s01
    for stage_id in ("S02", "S03"):
        affected = parse_stage_map_entry(plan, stage_id)
        assert (affected.status, affected.revision, affected.human_review_revision, affected.human_review_status) == ("PROPOSED", 2, 2, "PENDING"), affected
    feedback_state = parse_feedback_state(feedback)
    assert (feedback_state.latest_revision, feedback_state.mode) == (1, "none"), feedback_state
    assert (feedback_state.entries[0].status, feedback_state.entries[0].affected_stages) == ("applied", ("S02", "S03")), feedback_state
    system.assert_task_sequence(messages, ["orchestrator-discovery"])
    validate_fixture_state(plan, "S02", expected_plan=PlanFrontmatter("waiting-approval", "none"), expected_stage_status="PROPOSED")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md\nAPPROVE")
    state = parse_plan_frontmatter(plan)
    assert state == PlanFrontmatter("planning", "S02"), (state, messages)
    system.assert_task_sequence(messages, [])
finally:
    system.close()
print("plan feedback resume E2E passed")
