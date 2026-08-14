#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage, write_passed_human_review
from fixture_validation import assert_fixture_state, replace_required


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "none", "waiting-plan-approval")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_human_review(system.workspace, 1, "Value contract")
    replace_required(plan, "- Human review revision: 0", "- Human review revision: 1")
    replace_required(plan, "- Human review status: PENDING", "- Human review status: PASS")
    human_review = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.human-review.md"
    review = system.workspace / "1_orchestrator/e2e/reviews/01-human-review.md"
    assert_fixture_state(plan, "waiting-plan-approval", "none", "S01", {"Status": "PASS", "Revision": "1", "Human review revision": "1", "Human review status": "PASS"}, human_review, {"revision": "1", "source_revision": "1"}, review, {"stage_revision": "1", "source_revision": "1", "status": "PASS"})
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md\nAPPROVE PLAN")
    content = plan.read_text(encoding="utf-8")
    assert "status: ready" in content, (content, messages)
    assert "current_stage: none" in content, (content, messages)
    assert system.task_agents(messages) == []
print("plan approval E2E passed")
