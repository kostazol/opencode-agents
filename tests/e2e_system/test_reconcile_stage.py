#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PLANNING", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    review.unlink()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "- Status: REVIEW" in content, (content, messages)
    assert "- Revision: 1" in content
    assert system.task_agents(messages) == [], system.task_agents(messages)
print("stage reconciliation E2E passed")
