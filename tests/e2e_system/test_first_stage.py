#!/usr/bin/env python3

import re

from harness import SystemWorkspace, seed_plan
from fixture_validation import PlanFrontmatter, parse_technical_stage, validate_fixture_state


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PROPOSED", "Value contract"), ("PROPOSED", "Value consumer")], "S01")
    validate_fixture_state(plan, "S01", expected_plan=PlanFrontmatter("planning", "S01"), expected_stage_status="PROPOSED")
    validate_fixture_state(plan, "S02", expected_plan=PlanFrontmatter("planning", "S01"), expected_stage_status="PROPOSED")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    stages = list((system.workspace / "1_orchestrator/e2e/stages").glob("*.md"))
    assert len(stages) == 1, (stages, messages)
    content = stages[0].read_text(encoding="utf-8")
    stage = parse_technical_stage(stages[0])
    assert (stage.stage_id, stage.status, stage.revision) == ("S01", "REVIEW", 1), stage
    assert re.search(r"[А-Яа-яЁё]", content), content
    for heading in ("## Architecture", "## Reference patterns", "## Required", "## Key contracts", "### Consumes", "### Produces", "## Risks", "## Implementation outline", "## Required test scenarios", "## Acceptance signals", "## Verification", "## Implementation discretion"):
        assert heading in content, content
    for heading in ("Architecture", "Reference patterns", "Required", "Key contracts", "Risks", "Implementation outline", "Required test scenarios", "Acceptance signals", "Verification", "Implementation discretion"):
        match = re.search(rf"## {heading}\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
        assert match and match.group(1).strip(), content
    assert re.search(r"### Consumes\s*\n\S+", content), content
    assert re.search(r"### Produces\s*\n\S+", content), content
    assert "current_value()" in content and "int" in content, content
    for field in ("Вход/предусловия", "Действие", "Ожидаемый результат"):
        assert re.search(rf"`?{re.escape(field)}`?:", content), content
    system.assert_task_sequence(messages, ["orchestrator-stage-planner"])
print("first stage E2E passed")
