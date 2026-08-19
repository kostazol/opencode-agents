#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, mutate_artifact_frontmatter, mutate_stage_map_entry, parse_stage_map_entry, validate_fixture_state, write_technical_review


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PLANNING", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    stage = next((system.workspace / "1_orchestrator/e2e/stages").glob("01-*.md"))
    mutate_artifact_frontmatter(stage, revision=3)
    mutate_stage_map_entry(plan, "S01", revision=3)
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    write_technical_review(review, "S01", 3, "REVISE", "Add one missing deterministic validation detail.")
    validate_fixture_state(plan, "S01", stage, review, expected_plan=PlanFrontmatter("planning", "S01"), expected_stage_status="PLANNING", expected_artifact_status="REVIEW", expected_review_status="REVISE")
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    state = parse_stage_map_entry(plan, "S01")
    assert (state.revision, state.correction_source_revision) == (4, 3), (state, messages)
    system.assert_task_sequence(messages, [])
print("revision four E2E passed")
