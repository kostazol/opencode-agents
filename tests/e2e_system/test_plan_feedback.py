#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage, write_passed_human_review
from fixture_validation import PlanFrontmatter, mutate_stage_map_entry, parse_feedback_state, parse_plan_frontmatter, validate_fixture_state


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "none", "waiting-plan-approval")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_human_review(system.workspace, 1, "Value contract")
    mutate_stage_map_entry(plan, "S01", human_review_revision=1, human_review_status="PASS")
    human_review = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.human-review.md"
    review = system.workspace / "1_orchestrator/e2e/reviews/01-human-review.md"
    validate_fixture_state(plan, "S01", system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md", system.workspace / "1_orchestrator/e2e/reviews/01.md", expected_plan=PlanFrontmatter("waiting-plan-approval", "none"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS")
    validate_fixture_state(plan, "S01", human_review, review, human=True, expected_plan=PlanFrontmatter("waiting-plan-approval", "none"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS")
    system.start()
    remark = "Значение должно быть 2, а не 1."
    messages = system.run_transition(f"RESUME: 1_orchestrator/e2e/plan.md\n{remark}")
    feedback = system.workspace / "1_orchestrator/e2e/feedback.md"
    assert feedback.is_file(), (system.task_agents(messages), messages)
    feedback_state = parse_feedback_state(feedback)
    assert (feedback_state.latest_revision, feedback_state.mode) == (1, "PLAN_FEEDBACK"), feedback_state
    assert len(feedback_state.entries) == 1
    entry = feedback_state.entries[0]
    assert (entry.revision, entry.status, entry.remarks, entry.questions) == (1, "pending", remark, "none"), entry
    assert parse_plan_frontmatter(plan) == PlanFrontmatter("discovery", "none")
    system.assert_task_sequence(messages, [])
print("plan feedback E2E passed")
