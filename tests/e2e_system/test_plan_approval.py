#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage, write_passed_human_review
from fixture_validation import PlanFrontmatter, mutate_stage_map_entry, parse_plan_frontmatter, validate_fixture_state


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
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md\nAPPROVE PLAN")
    state = parse_plan_frontmatter(plan)
    assert state == PlanFrontmatter("ready", "none"), (state, messages)
    system.assert_task_sequence(messages, [])
print("plan approval E2E passed")
