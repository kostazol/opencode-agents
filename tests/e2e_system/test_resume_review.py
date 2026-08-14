#!/usr/bin/env python3

import re

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import assert_fixture_state


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
    assert_fixture_state(plan, "planning", "S01", "S01", {"Status": "REVIEW", "Revision": "1"}, stage, {"revision": "1"})
    assert not review.exists(), review
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/requested/plan.md")
    assert review.is_file(), (system.task_agents(messages), messages)
    review_content = review.read_text(encoding="utf-8")
    assert "stage: S01" in review_content
    assert "status: PASS" in review_content
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
