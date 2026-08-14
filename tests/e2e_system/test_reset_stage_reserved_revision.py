#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract"), ("PROPOSED", "Value consumer")], "S02", "planning")
    write_passed_stage(system.workspace, 1, "Value contract")
    plan.write_text(plan.read_text(encoding="utf-8").replace("### S02 — Потребитель значения\n- Status: PROPOSED\n- Revision: 0", "### S02 — Потребитель значения\n- Status: PROPOSED\n- Revision: 2"), encoding="utf-8")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    stage = system.workspace / "1_orchestrator/e2e/stages/02-value-consumer.md"
    assert stage.is_file(), (system.task_agents(messages), messages)
    assert "revision: 2" in stage.read_text(encoding="utf-8"), stage.read_text(encoding="utf-8")
    assert "- Revision: 2" in plan.read_text(encoding="utf-8"), plan.read_text(encoding="utf-8")
    assert system.task_agents(messages)[:1] == ["orchestrator-stage-planner"], system.task_agents(messages)
print("reset stage reserved revision E2E passed")
