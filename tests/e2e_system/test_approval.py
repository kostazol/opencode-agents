#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan
from fixture_validation import PlanFrontmatter, parse_plan_frontmatter, validate_fixture_state


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PROPOSED", "Value contract"), ("PROPOSED", "Value consumer")], "none", "waiting-approval")
    validate_fixture_state(plan, "S01", expected_plan=PlanFrontmatter("waiting-approval", "none"), expected_stage_status="PROPOSED")
    validate_fixture_state(plan, "S02", expected_plan=PlanFrontmatter("waiting-approval", "none"), expected_stage_status="PROPOSED")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md\nAPPROVE")
    state = parse_plan_frontmatter(plan)
    assert state == PlanFrontmatter("planning", "S01"), (state, messages)
    system.assert_task_sequence(messages, [])
timing = system.timing_result()
assert {"fixture_setup", "environment_setup", "process_startup_to_health", "agent_inventory_loading", "prompt_to_idle", "prompt_or_answer_to_idle", "cleanup", "test_case_total"}.issubset(timing["durations_seconds"]), timing
assert timing["sessions_created"] == 1 and timing["task_calls"] == 0 and timing["successful_task_calls"] == 0 and timing["task_agent_names"] == [], timing
print("approval E2E passed")
