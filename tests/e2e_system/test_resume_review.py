#!/usr/bin/env python3

import re

from harness import SystemWorkspace, seed_plan, write_passed_stage


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("REVIEW", "Value contract")], "S01")
    write_passed_stage(system.workspace, 1, "Value contract")
    requested = system.workspace / "1_orchestrator/requested"
    (system.workspace / "1_orchestrator/e2e").rename(requested)
    plan = requested / "plan.md"
    decoy = seed_plan(system.workspace, [("PROPOSED", "Decoy value")], "S01")
    decoy_before = decoy.read_text(encoding="utf-8")
    review = requested / "reviews/01.md"
    review.unlink()
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Revision: 0", "- Revision: 1"), encoding="utf-8")
    stage = requested / "stages/01-value-contract.md"
    stage.write_text(stage.read_text(encoding="utf-8") + "\n## Expected paths\n\n- `src/future_value.py` — planned new product file; currently absent.\n", encoding="utf-8")
    messages = system.run_transition("RESUME: 1_orchestrator/requested/plan.md")
    assert review.is_file(), (system.task_agents(messages), messages)
    review_content = review.read_text(encoding="utf-8")
    assert "stage: S01" in review_content
    assert "status: BLOCKED" not in review_content
    assert re.search(r"[А-Яа-яЁё]", review_content), review_content
    assert decoy.read_text(encoding="utf-8") == decoy_before
    assert not (system.workspace / "WORKFLOW_BASE").exists()
    assert system.task_agents(messages) == ["orchestrator-stage-reviewer"]
    task_inputs = [part.get("state", {}).get("input", {}) for message in messages for part in message.get("parts", []) if isinstance(part, dict) and part.get("type") == "tool" and part.get("tool") == "task"]
    required_paths = ("1_orchestrator/requested/plan.md", "1_orchestrator/requested/discovery.md", "1_orchestrator/requested/stages/01-value-contract.md", "1_orchestrator/requested/reviews/01.md")
    assert all(all(path in item.get("prompt", "") for path in required_paths) for item in task_inputs), task_inputs
    assert all("1_orchestrator/e2e/" not in item.get("prompt", "") for item in task_inputs), task_inputs
print("resume review E2E passed")
