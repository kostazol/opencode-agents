#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("REVIEW", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    stage = next((system.workspace / "1_orchestrator/e2e/stages").glob("01-*.md"))
    stage.write_text(stage.read_text(encoding="utf-8").replace("revision: 1", "revision: 3"), encoding="utf-8")
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Revision: 0", "- Revision: 3"), encoding="utf-8")
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    review.write_text("---\nstage: S01\nstage_revision: 3\nstatus: REVISE\n---\n\n# Review S01\n\n## Findings\n- Validation remains incomplete.\n", encoding="utf-8")
    messages = system.run_step("MODE: STEP\nRESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "status: blocked" in content, (content, messages)
    assert "- Status: BLOCKED" in content
    assert system.task_agents(messages) == []
print("revision limit E2E passed")
