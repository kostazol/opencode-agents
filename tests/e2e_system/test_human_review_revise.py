#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage, write_passed_human_review


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "S01", "human-reviewing")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_human_review(system.workspace, 1, "Value contract")
    human_review = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.human-review.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Human review revision: 0", "- Human review revision: 1").replace("- Human review status: PENDING", "- Human review status: REVIEW"), encoding="utf-8")
    review = system.workspace / "1_orchestrator/e2e/reviews/01-human-review.md"
    review.write_text("---\nstage: S01\nstage_revision: 1\nsource_revision: 1\nstatus: REVISE\n---\n\n# Review S01\n\n## Findings\n- Явно укажите отсутствие изменения состояния.\n", encoding="utf-8")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "- Human review revision: 2" in content, (content, messages)
    assert "- Human review correction source revision: 1" in content, (content, messages)
    assert "revision: 1" in human_review.read_text(encoding="utf-8")
    assert system.task_agents(messages) == []
print("human review revise E2E passed")
