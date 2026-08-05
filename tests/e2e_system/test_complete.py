#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract"), ("PASS", "Value consumer")], "S02")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_stage(system.workspace, 2, "Value consumer")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "status: ready" in content
    assert "current_stage: none" in content
    assert system.task_agents(messages) == []
print("complete workflow E2E passed")
