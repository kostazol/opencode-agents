#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import assert_fixture_state


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PLANNING", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    stage = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md"
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    review.write_text("---\nstage: S01\nstage_revision: 1\nstatus: REVISE\n---\n\n# Review S01\n\n## Findings\n- Add an exact validation command and expected result.\n", encoding="utf-8")
    assert_fixture_state(plan, "planning", "S01", "S01", {"Status": "PLANNING", "Revision": "1"}, stage, {"revision": "1"}, review, {"stage_revision": "1", "status": "REVISE"})
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "- Revision: 2" in content, (content, messages)
    assert "- Correction source revision: 1" in content, (content, messages)
    system.assert_task_sequence(messages, [])
print("plan revision E2E passed")
