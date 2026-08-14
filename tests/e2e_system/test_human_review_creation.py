#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "S01", "human-reviewing")
    write_passed_stage(system.workspace, 1, "Value contract")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    human_review = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.human-review.md"
    assert human_review.is_file(), (system.task_agents(messages), messages)
    content = human_review.read_text(encoding="utf-8")
    assert "source_revision: 1" in content, content
    assert "## Что я получу после этапа" in content, content
    assert system.task_agents(messages) == ["orchestrator-stage-planner"]
print("human review creation E2E passed")
