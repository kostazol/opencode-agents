#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import assert_fixture_state, replace_required


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PLANNING", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    stage = next((system.workspace / "1_orchestrator/e2e/stages").glob("01-*.md"))
    replace_required(stage, "revision: 1", "revision: 3")
    replace_required(plan, "- Revision: 1", "- Revision: 3")
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    review.write_text("---\nstage: S01\nstage_revision: 3\nstatus: REVISE\n---\n\n# Review S01\n\n## Findings\n- Add one missing deterministic validation detail.\n", encoding="utf-8")
    assert_fixture_state(plan, "planning", "S01", "S01", {"Status": "PLANNING", "Revision": "3"}, stage, {"revision": "3"}, review, {"stage_revision": "3", "status": "REVISE"})
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "- Revision: 4" in content, (content, messages)
    assert "- Correction source revision: 3" in content, (content, messages)
    system.assert_task_sequence(messages, [])
print("revision four E2E passed")
