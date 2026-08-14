#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_human_review, write_passed_stage
from fixture_validation import assert_fixture_state, replace_required


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "S01", "human-reviewing")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_human_review(system.workspace, 1, "Value contract")
    human_review = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.human-review.md"
    replace_required(human_review, "source_revision: 1", "source_revision: 0")
    replace_required(plan, "- Human review revision: 0", "- Human review revision: 1")
    review = system.workspace / "1_orchestrator/e2e/reviews/01-human-review.md"
    assert_fixture_state(plan, "human-reviewing", "S01", "S01", {"Status": "PASS", "Revision": "1", "Human review revision": "1", "Human review status": "PENDING"}, human_review, {"revision": "1", "source_revision": "0"}, review, {"stage_revision": "1", "source_revision": "1", "status": "PASS"})
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "- Human review revision: 2" in content, (content, messages)
    assert "- Human review mismatch source revision: 1" in content, content
    system.assert_task_sequence(messages, [])
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "- Human review revision: 2" in content, (content, messages)
    assert "- Human review revision: 3" not in content, content
    system.assert_task_sequence(messages, ["orchestrator-stage-planner"])
    corrected = human_review.read_text(encoding="utf-8")
    assert "revision: 2" in corrected and "source_revision: 1" in corrected, corrected
    assert "- Human review status: REVIEW" in content, content
print("human review mismatch resume E2E passed")
