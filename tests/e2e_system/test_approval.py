#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PROPOSED", "Value contract"), ("PROPOSED", "Value consumer")], "none", "waiting-approval")
    messages = system.run_step("MODE: STEP\nRESUME: 1_orchestrator/e2e/plan.md\nAPPROVE")
    content = plan.read_text(encoding="utf-8")
    assert "status: planning" in content, (content, messages)
    assert "current_stage: S01" in content, (content, messages)
    assert system.task_agents(messages) == []
print("approval E2E passed")
