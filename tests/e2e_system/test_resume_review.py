#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("REVIEW", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    review.unlink()
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Revision: 0", "- Revision: 1"), encoding="utf-8")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    assert review.is_file()
    assert "stage: S01" in review.read_text(encoding="utf-8")
    assert system.task_agents(messages) == ["orchestrator-stage-reviewer"]
print("resume review E2E passed")
