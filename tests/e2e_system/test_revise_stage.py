#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, parse_plan_frontmatter, parse_stage_map_entry, parse_technical_stage, validate_fixture_state, write_technical_review


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("REVIEW", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    stage = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md"
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    technical_review = write_technical_review(review, "S01", 1, "REVISE", "Add an exact validation command and expected result.")
    validate_fixture_state(plan, "S01", stage, review, expected_plan=PlanFrontmatter("planning", "S01"), expected_stage_status="REVIEW", expected_artifact_status="REVIEW", expected_review_status="REVISE")
    assert parse_technical_stage(stage).revision == technical_review.stage_revision == 1
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    stage_entry = parse_stage_map_entry(plan, "S01")
    assert stage_entry.status == "PLANNING", (stage_entry, messages)
    system.assert_task_sequence(messages, [])
print("revise routing E2E passed")
