#!/usr/bin/env python3

import re

from harness import SystemWorkspace, seed_plan, write_passed_stage


def remove_human_review_fields(content: str) -> str:
    return re.sub(r"\n- Human review:.*\n- Human review revision:.*\n- Human review status:.*\n- Human review review:.*", "", content)


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "none", "ready")
    write_passed_stage(system.workspace, 1, "Value contract")
    plan.write_text(remove_human_review_fields(plan.read_text(encoding="utf-8")), encoding="utf-8")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "status: human-reviewing" in content, (content, messages)
    assert "current_stage: S01" in content, content
    assert "- Human review: stages/01-value-contract.human-review.md" in content, content
    assert "- Human review revision: 0" in content, content
    assert "- Human review status: PENDING" in content, content
    assert "- Human review review: reviews/01-human-review.md" in content, content
    system.assert_task_sequence(messages, [])

with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PLANNING", "Value contract")], "S01", "planning")
    plan.write_text(remove_human_review_fields(plan.read_text(encoding="utf-8")), encoding="utf-8")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    content = plan.read_text(encoding="utf-8")
    assert "status: planning" in content, (content, messages)
    assert "current_stage: S01" in content, content
    assert "- Status: PLANNING" in content, content
    assert "- Human review revision: 0" in content, content
    assert "- Human review status: PENDING" in content, content
    system.assert_task_sequence(messages, [])
print("legacy human review migration E2E passed")
