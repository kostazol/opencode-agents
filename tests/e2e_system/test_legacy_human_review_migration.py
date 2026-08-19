#!/usr/bin/env python3

import re

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, parse_plan_frontmatter, parse_stage_map, parse_stage_map_entry, write_intentionally_malformed_fixture


def remove_human_review_fields(content: str) -> str:
    return re.sub(r"\n- Human review:.*\n- Human review revision:.*\n- Human review status:.*\n- Human review review:.*", "", content)


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "none", "ready")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_intentionally_malformed_fixture(plan, remove_human_review_fields(plan.read_text(encoding="utf-8")), reason="Exercise migration from legacy stage maps without human-review fields.", parser=parse_stage_map, expected_error=r"field=S01.Human review")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    state = parse_plan_frontmatter(plan)
    stage = parse_stage_map_entry(plan, "S01")
    assert state == PlanFrontmatter("human-reviewing", "S01"), (state, messages)
    assert (stage.human_review, stage.human_review_revision, stage.human_review_status, stage.human_review_review) == ("stages/01-value-contract.human-review.md", 0, "PENDING", "reviews/01-human-review.md"), stage
    system.assert_task_sequence(messages, [])

with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PLANNING", "Value contract")], "S01", "planning")
    write_intentionally_malformed_fixture(plan, remove_human_review_fields(plan.read_text(encoding="utf-8")), reason="Exercise planning-state migration from legacy stage maps without human-review fields.", parser=parse_stage_map, expected_error=r"field=S01.Human review")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    state = parse_plan_frontmatter(plan)
    stage = parse_stage_map_entry(plan, "S01")
    assert state == PlanFrontmatter("planning", "S01"), (state, messages)
    assert (stage.status, stage.human_review_revision, stage.human_review_status) == ("PLANNING", 0, "PENDING"), stage
    system.assert_task_sequence(messages, [])
print("legacy human review migration E2E passed")
