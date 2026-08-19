#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, parse_stage_map_entry, validate_fixture_state, write_technical_review


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PLANNING", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    stage = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md"
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    write_technical_review(review, "S01", 1, "REVISE", "Add an exact validation command and expected result.")
    validate_fixture_state(plan, "S01", stage, review, expected_plan=PlanFrontmatter("planning", "S01"), expected_stage_status="PLANNING", expected_artifact_status="REVIEW", expected_review_status="REVISE")
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    state = parse_stage_map_entry(plan, "S01")
    assert (state.revision, state.correction_source_revision) == (2, 1), (state, messages)
    system.assert_task_sequence(messages, [])
print("plan revision E2E passed")
