#!/usr/bin/env python3

import re

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, parse_technical_review, parse_technical_stage, validate_fixture_state


with SystemWorkspace(start_on_enter=False, expected_request="requested") as system:
    plan = seed_plan(system.workspace, [("REVIEW", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    requested = system.workspace / "1_orchestrator/requested"
    (system.workspace / "1_orchestrator/e2e").rename(requested)
    plan = requested / "plan.md"
    decoy = seed_plan(system.workspace, [("PROPOSED", "Decoy value")], "S01")
    decoy_before = decoy.read_text(encoding="utf-8")
    review = requested / "reviews/01.md"
    review.unlink()
    stage = requested / "stages/01-value-contract.md"
    assert "Имена test cases" in stage.read_text(encoding="utf-8")
    validate_fixture_state(plan, "S01", stage, expected_plan=PlanFrontmatter("planning", "S01"), expected_stage_status="REVIEW", expected_artifact_status="REVIEW")
    validate_fixture_state(decoy, "S01", expected_plan=PlanFrontmatter("planning", "S01"), expected_stage_status="PROPOSED")
    assert not review.exists(), review
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/requested/plan.md")
    assert review.is_file(), (system.task_agents(messages), messages)
    review_content = review.read_text(encoding="utf-8")
    review_state = parse_technical_review(review)
    assert (review_state.stage_id, review_state.stage_revision, review_state.status) == ("S01", 1, "PASS"), review_state
    assert "## Findings\n- Нет." in review_content
    for check in ("Результат и границы", "Архитектурный подход", "Образцы и доказательства", "Обязательные контракты", "Риски и ограничения", "Бизнес-сценарии и валидации", "Проверяемость результата", "Уровень детализации"):
        assert f"- {check}: PASS" in review_content, review_content
    assert re.search(r"[А-Яа-яЁё]", review_content), review_content
    assert decoy.read_text(encoding="utf-8") == decoy_before
    assert not (system.workspace / "WORKFLOW_BASE").exists()
    calls = system.assert_task_sequence(messages, ["orchestrator-stage-reviewer"])
    task_inputs = [call.input for call in calls if call.input is not None]
    required_paths = ("1_orchestrator/requested/plan.md", "1_orchestrator/requested/discovery.md", "1_orchestrator/requested/stages/01-value-contract.md", "1_orchestrator/requested/reviews/01.md")
    assert all(all(path in item.get("prompt", "") for path in required_paths) for item in task_inputs), task_inputs
    assert all("1_orchestrator/e2e/" not in item.get("prompt", "") for item in task_inputs), task_inputs
print("resume review E2E passed")
