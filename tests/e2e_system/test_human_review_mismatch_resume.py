#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_human_review, write_passed_stage


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "S01", "human-reviewing")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_human_review(system.workspace, 1, "Value contract")
    human_review = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.human-review.md"
    human_review.write_text(human_review.read_text(encoding="utf-8").replace("source_revision: 1", "source_revision: 0"), encoding="utf-8")
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Human review revision: 0", "- Human review revision: 1"), encoding="utf-8")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "- Human review revision: 2" in content, (content, messages)
    assert "- Human review mismatch source revision: 1" in content, content
    assert system.task_agents(messages) == [], system.task_agents(messages)
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "- Human review revision: 2" in content, (content, messages)
    assert "- Human review revision: 3" not in content, content
    assert system.task_agents(messages) == ["orchestrator-stage-planner"], system.task_agents(messages)
    corrected = human_review.read_text(encoding="utf-8")
    assert "revision: 2" in corrected and "source_revision: 1" in corrected, corrected
    assert "- Human review status: REVIEW" in content, content
print("human review mismatch resume E2E passed")
