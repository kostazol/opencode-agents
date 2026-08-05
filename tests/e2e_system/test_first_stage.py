#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan


with SystemWorkspace() as system:
    seed_plan(system.workspace, [("PROPOSED", "Value contract"), ("PROPOSED", "Value consumer")], "S01")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    stages = list((system.workspace / "1_orchestrator/e2e/stages").glob("*.md"))
    assert len(stages) == 1, (stages, messages)
    assert "stage: S01" in stages[0].read_text(encoding="utf-8")
    assert system.task_agents(messages) == ["orchestrator-stage-planner"]
print("first stage E2E passed")
