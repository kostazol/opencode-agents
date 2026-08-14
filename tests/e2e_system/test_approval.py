#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PROPOSED", "Value contract"), ("PROPOSED", "Value consumer")], "none", "waiting-approval")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md\nAPPROVE")
    content = plan.read_text(encoding="utf-8")
    assert "status: planning" in content, (content, messages)
    assert "current_stage: S01" in content, (content, messages)
    assert system.task_agents(messages) == []
timing = system.timing_result()
assert {"fixture_setup", "environment_setup", "process_startup_to_health", "agent_inventory_loading", "prompt_to_idle", "prompt_or_answer_to_idle", "cleanup", "test_case_total"}.issubset(timing["durations_seconds"]), timing
assert timing["sessions_created"] == 1 and timing["task_calls"] == 0 and timing["task_agent_names"] == [], timing
print("approval E2E passed")
