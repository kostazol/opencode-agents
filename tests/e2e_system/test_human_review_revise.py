#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage, write_passed_human_review
from fixture_validation import PlanFrontmatter, mutate_stage_map_entry, parse_human_review, parse_stage_map_entry, validate_fixture_state, write_human_review_review


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "S01", "human-reviewing")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_human_review(system.workspace, 1, "Value contract")
    human_review = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.human-review.md"
    mutate_stage_map_entry(plan, "S01", human_review_revision=1, human_review_status="REVIEW")
    review = system.workspace / "1_orchestrator/e2e/reviews/01-human-review.md"
    review_state = write_human_review_review(review, "S01", 1, 1, "REVISE", "Явно укажите отсутствие изменения состояния.")
    validate_fixture_state(plan, "S01", system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md", system.workspace / "1_orchestrator/e2e/reviews/01.md", expected_plan=PlanFrontmatter("human-reviewing", "S01"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS")
    validate_fixture_state(plan, "S01", human_review, review, human=True, expected_plan=PlanFrontmatter("human-reviewing", "S01"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="REVISE")
    assert review_state.status == "REVISE"
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    stage = parse_stage_map_entry(plan, "S01")
    assert (stage.human_review_revision, stage.human_review_correction_source_revision) == (2, 1), (stage, messages)
    assert parse_human_review(human_review).revision == 1
    system.assert_task_sequence(messages, [])
print("human review revise E2E passed")
