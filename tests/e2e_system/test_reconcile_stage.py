#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, parse_stage_map_entry, validate_fixture_state


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PLANNING", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    review.unlink()
    validate_fixture_state(plan, "S01", system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md", expected_plan=PlanFrontmatter("planning", "S01"), expected_stage_status="PLANNING", expected_artifact_status="REVIEW")
    assert not review.exists(), review
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    stage = parse_stage_map_entry(plan, "S01")
    assert (stage.status, stage.revision) == ("REVIEW", 1), (stage, messages)
    system.assert_task_sequence(messages, [])
print("stage reconciliation E2E passed")
