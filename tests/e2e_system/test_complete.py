#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, parse_plan_frontmatter, validate_fixture_state


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract"), ("PASS", "Value consumer")], "S02")
    write_passed_stage(system.workspace, 1, "Value contract")
    write_passed_stage(system.workspace, 2, "Value consumer")
    for number, title in enumerate(("value-contract", "value-consumer"), start=1):
        validate_fixture_state(plan, f"S{number:02d}", system.workspace / f"1_orchestrator/e2e/stages/{number:02d}-{title}.md", system.workspace / f"1_orchestrator/e2e/reviews/{number:02d}.md", expected_plan=PlanFrontmatter("planning", "S02"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    state = parse_plan_frontmatter(plan)
    assert state == PlanFrontmatter("human-reviewing", "S01"), (state, messages)
    system.assert_task_sequence(messages, [])
print("human review phase E2E passed")
