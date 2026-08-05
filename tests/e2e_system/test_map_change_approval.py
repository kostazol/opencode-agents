#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract"), ("MAP_CHANGE_REQUIRED", "Value consumer"), ("PROPOSED", "Value docs")], "S02", "waiting-map-approval")
    write_passed_stage(system.workspace, 1, "Value contract")
    with plan.open("a", encoding="utf-8") as output:
        output.write("\n## Pending map change\n\n- Source: reviews/02.md\n- Evidence: consumer and docs share one observable contract.\n- Affected stages: S02, S03\n- Replacement entries:\n  - S02 — Value consumer and docs; Depends on S01; Consumes value contract; Produces documented value contract.\n")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md\nAPPROVE MAP CHANGE")
    content = plan.read_text(encoding="utf-8")
    assert "status: planning" in content, (content, messages)
    assert "current_stage: S02" in content
    assert "- Status: PROPOSED" in content
    assert system.task_agents(messages) == []
print("map change approval E2E passed")
