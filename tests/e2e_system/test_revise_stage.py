#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("REVIEW", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Revision: 0", "- Revision: 1"), encoding="utf-8")
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    review.write_text("---\nstage: S01\nstage_revision: 1\nstatus: REVISE\n---\n\n# Review S01\n\n## Findings\n- Add an exact validation command and expected result.\n", encoding="utf-8")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "- Status: PLANNING" in content, (content, messages)
    assert system.task_agents(messages) == []
print("revise routing E2E passed")
