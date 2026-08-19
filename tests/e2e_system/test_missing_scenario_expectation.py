#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, parse_technical_review, parse_technical_stage, replace_required, validate_fixture_state


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("REVIEW", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    review.unlink()
    stage = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md"
    replace_required(stage, "- Ожидаемый результат: возвращается целое число `1`, состояние не меняется.\n", "")
    validate_fixture_state(plan, "S01", stage, expected_plan=PlanFrontmatter("planning", "S01"), expected_stage_status="REVIEW", expected_artifact_status="REVIEW")
    assert parse_technical_stage(stage).revision == 1
    assert not review.exists(), review
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    assert review.is_file(), (system.task_agents(messages), messages)
    review_content = review.read_text(encoding="utf-8")
    review_state = parse_technical_review(review)
    assert (review_state.stage_id, review_state.stage_revision, review_state.status) == ("S01", 1, "REVISE"), review_state
    assert "Ожидаемый результат" in review_content, review_content
    system.assert_task_sequence(messages, ["orchestrator-stage-reviewer"])
print("missing scenario expectation E2E passed")
