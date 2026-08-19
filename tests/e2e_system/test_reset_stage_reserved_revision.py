#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, mutate_stage_map_entry, parse_stage_map_entry, parse_technical_stage, validate_fixture_state


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract"), ("PROPOSED", "Value consumer")], "S02", "planning")
    write_passed_stage(system.workspace, 1, "Value contract")
    mutate_stage_map_entry(plan, "S02", revision=2)
    validate_fixture_state(plan, "S01", system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md", system.workspace / "1_orchestrator/e2e/reviews/01.md", expected_plan=PlanFrontmatter("planning", "S02"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS")
    validate_fixture_state(plan, "S02", expected_plan=PlanFrontmatter("planning", "S02"), expected_stage_status="PROPOSED")
    assert not (system.workspace / "1_orchestrator/e2e/stages/02-value-consumer.md").exists()
    assert not (system.workspace / "1_orchestrator/e2e/reviews/02.md").exists()
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    stage = system.workspace / "1_orchestrator/e2e/stages/02-value-consumer.md"
    assert stage.is_file(), (system.task_agents(messages), messages)
    assert parse_technical_stage(stage).revision == 2
    assert parse_stage_map_entry(plan, "S02").revision == 2
    system.assert_task_sequence(messages, ["orchestrator-stage-planner"])
print("reset stage reserved revision E2E passed")
