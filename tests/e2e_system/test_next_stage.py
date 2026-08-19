#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, parse_technical_stage, validate_fixture_state


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract"), ("PROPOSED", "Value consumer")], "S02")
    write_passed_stage(system.workspace, 1, "Value contract")
    validate_fixture_state(plan, "S01", system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md", system.workspace / "1_orchestrator/e2e/reviews/01.md", expected_plan=PlanFrontmatter("planning", "S02"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS")
    validate_fixture_state(plan, "S02", expected_plan=PlanFrontmatter("planning", "S02"), expected_stage_status="PROPOSED")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    second = list((system.workspace / "1_orchestrator/e2e/stages").glob("02-*.md"))
    assert len(second) == 1, second
    state = parse_technical_stage(second[0])
    assert (state.stage_id, state.status, state.revision) == ("S02", "REVIEW", 1), state
    system.assert_task_sequence(messages, ["orchestrator-stage-planner"])
print("next stage E2E passed")
