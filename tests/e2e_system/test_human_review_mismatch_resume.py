#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_human_review, write_passed_stage
from fixture_validation import PlanFrontmatter, assert_intentionally_malformed_fixture, mutate_artifact_frontmatter, mutate_stage_map_entry, parse_human_review, parse_stage_map_entry, validate_fixture_state


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "S01", "human-reviewing")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_human_review(system.workspace, 1, "Value contract")
    human_review = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.human-review.md"
    mutate_artifact_frontmatter(human_review, source_revision=0)
    mutate_stage_map_entry(plan, "S01", human_review_revision=1)
    review = system.workspace / "1_orchestrator/e2e/reviews/01-human-review.md"
    validate_fixture_state(plan, "S01", system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md", system.workspace / "1_orchestrator/e2e/reviews/01.md", expected_plan=PlanFrontmatter("human-reviewing", "S01"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS", invariant_opt_out_reason="Exercise stale human-review source revision recovery.", expected_invariant_error="human-review source revision 0 does not match technical revision 1")
    assert parse_human_review(human_review).source_revision == 0
    assert_intentionally_malformed_fixture(human_review, reason="Exercise stale human-review source revision recovery.", parser=lambda _: validate_fixture_state(plan, "S01", human_review, review, human=True, expected_plan=PlanFrontmatter("human-reviewing", "S01"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS", invariant_opt_out_reason="Exercise lower-level source revision diagnostic.", expected_invariant_error="human-review source revision 0 does not match technical revision 1"), expected_error=r"field=source_revision; value=0; expected indexed technical revision 1")
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    state = parse_stage_map_entry(plan, "S01")
    assert (state.human_review_revision, state.human_review_mismatch_source_revision) == (2, 1), (state, messages)
    system.assert_task_sequence(messages, [])
    assert_intentionally_malformed_fixture(human_review, reason="Resume reserved revision with stale human-review artifact.", parser=lambda _: validate_fixture_state(plan, "S01", human_review, review, human=True, expected_plan=PlanFrontmatter("human-reviewing", "S01"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS"), expected_error=r"field=source_revision; value=0; expected indexed technical revision 1")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    state = parse_stage_map_entry(plan, "S01")
    assert state.human_review_revision == 2, (state, messages)
    system.assert_task_sequence(messages, ["orchestrator-stage-planner"])
    corrected = parse_human_review(human_review)
    assert (corrected.revision, corrected.source_revision) == (2, 1), corrected
    assert state.human_review_status == "REVIEW", state
print("human review mismatch resume E2E passed")
