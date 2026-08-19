#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage, write_passed_human_review
from fixture_validation import PlanFrontmatter, mutate_stage_map_entry, parse_human_review, parse_human_review_review, validate_fixture_state


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "S01", "human-reviewing")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_human_review(system.workspace, 1, "Value contract")
    review = system.workspace / "1_orchestrator/e2e/reviews/01-human-review.md"
    review.unlink()
    mutate_stage_map_entry(plan, "S01", human_review_revision=1, human_review_status="REVIEW")
    human_review = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.human-review.md"
    validate_fixture_state(plan, "S01", system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md", system.workspace / "1_orchestrator/e2e/reviews/01.md", expected_plan=PlanFrontmatter("human-reviewing", "S01"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS")
    validate_fixture_state(plan, "S01", human_review, human=True, expected_plan=PlanFrontmatter("human-reviewing", "S01"), expected_stage_status="PASS", expected_artifact_status="REVIEW")
    assert not review.exists(), review
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    assert review.is_file(), (system.task_agents(messages), messages)
    review_content = review.read_text(encoding="utf-8")
    review_state = parse_human_review_review(review)
    assert (review_state.stage_id, review_state.status, review_state.stage_revision, review_state.source_revision) == ("S01", "PASS", 1, 1), review_state
    for check in ("Соответствие техническому плану", "Итог этапа и практическая работа", "Сценарии, ошибки и изменения состояния", "Границы, риски и вопросы для подтверждения", "Понятность без глубоких технических знаний"):
        assert f"- {check}: PASS" in review_content, review_content
    system.assert_task_sequence(messages, ["orchestrator-stage-reviewer"])
print("human review gate E2E passed")
