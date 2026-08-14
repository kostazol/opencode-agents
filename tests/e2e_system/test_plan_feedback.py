#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage, write_passed_human_review


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "none", "waiting-plan-approval")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_human_review(system.workspace, 1, "Value contract")
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Human review revision: 0", "- Human review revision: 1").replace("- Human review status: PENDING", "- Human review status: PASS"), encoding="utf-8")
    remark = "Значение должно быть 2, а не 1."
    messages = system.run_transition(f"RESUME: 1_orchestrator/e2e/plan.md\n{remark}")
    feedback = system.workspace / "1_orchestrator/e2e/feedback.md"
    assert feedback.is_file(), (system.task_agents(messages), messages)
    feedback_content = feedback.read_text(encoding="utf-8")
    for expected in ("latest_revision: 1", "mode: PLAN_FEEDBACK", "## Feedback 1", "Status: pending", remark, "Affected stages:", "Questions: none"):
        assert expected in feedback_content, feedback_content
    assert "status: discovery" in plan.read_text(encoding="utf-8")
print("plan feedback E2E passed")
