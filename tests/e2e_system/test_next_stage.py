#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage


with SystemWorkspace() as system:
    seed_plan(system.workspace, [("PASS", "Value contract"), ("PROPOSED", "Value consumer")], "S02")
    write_passed_stage(system.workspace, 1, "Value contract")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    second = list((system.workspace / "1_orchestrator/e2e/stages").glob("02-*.md"))
    assert len(second) == 1, second
    assert "stage: S02" in second[0].read_text(encoding="utf-8")
    system.assert_task_sequence(messages, ["orchestrator-stage-planner"])
print("next stage E2E passed")
