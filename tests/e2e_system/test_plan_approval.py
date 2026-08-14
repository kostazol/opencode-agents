#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage, write_passed_human_review


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "none", "waiting-plan-approval")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_human_review(system.workspace, 1, "Value contract")
    content = plan.read_text(encoding="utf-8").replace("- Human review revision: 0", "- Human review revision: 1").replace("- Human review status: PENDING", "- Human review status: PASS")
    plan.write_text(content, encoding="utf-8")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md\nAPPROVE PLAN")
    content = plan.read_text(encoding="utf-8")
    assert "status: ready" in content, (content, messages)
    assert "current_stage: none" in content, (content, messages)
    assert system.task_agents(messages) == []
print("plan approval E2E passed")
