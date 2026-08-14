#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage, write_passed_human_review
from fixture_validation import assert_fixture_state, replace_required


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "S01", "human-reviewing")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_human_review(system.workspace, 1, "Value contract")
    review = system.workspace / "1_orchestrator/e2e/reviews/01-human-review.md"
    review.unlink()
    replace_required(plan, "- Human review revision: 0", "- Human review revision: 1")
    replace_required(plan, "- Human review status: PENDING", "- Human review status: REVIEW")
    human_review = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.human-review.md"
    assert_fixture_state(plan, "human-reviewing", "S01", "S01", {"Status": "PASS", "Revision": "1", "Human review revision": "1", "Human review status": "REVIEW"}, human_review, {"revision": "1", "source_revision": "1"})
    assert not review.exists(), review
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    assert review.is_file(), (system.task_agents(messages), messages)
    review_content = review.read_text(encoding="utf-8")
    assert "status: PASS" in review_content, review_content
    assert "stage_revision: 1" in review_content, review_content
    assert "source_revision: 1" in review_content, review_content
    for check in ("Соответствие техническому плану", "Итог этапа и практическая работа", "Сценарии, ошибки и изменения состояния", "Границы, риски и вопросы для подтверждения", "Понятность без глубоких технических знаний"):
        assert f"- {check}: PASS" in review_content, review_content
    assert system.task_agents(messages) == ["orchestrator-stage-reviewer"]
print("human review gate E2E passed")
