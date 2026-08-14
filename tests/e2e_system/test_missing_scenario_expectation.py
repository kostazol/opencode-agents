#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("REVIEW", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    review.unlink()
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Revision: 0", "- Revision: 1"), encoding="utf-8")
    stage = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md"
    stage.write_text(stage.read_text(encoding="utf-8").replace("- Ожидаемый результат: возвращается целое число `1`, состояние не меняется.\n", ""), encoding="utf-8")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    assert review.is_file(), (system.task_agents(messages), messages)
    review_content = review.read_text(encoding="utf-8")
    assert "status: REVISE" in review_content, review_content
    assert "Ожидаемый результат" in review_content, review_content
    agents = system.task_agents(messages)
    assert 1 <= len(agents) <= 2 and set(agents) == {"orchestrator-stage-reviewer"}, agents
print("missing scenario expectation E2E passed")
