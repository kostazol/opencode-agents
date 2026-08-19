#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, mutate_artifact_frontmatter, mutate_stage_map_entry, parse_plan_frontmatter, parse_stage_map_entry, validate_fixture_state, write_technical_review


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("BLOCKED", "Value contract")], "S01", "blocked")
    write_passed_stage(system.workspace, 1, "Value contract")
    stage = next((system.workspace / "1_orchestrator/e2e/stages").glob("01-*.md"))
    mutate_artifact_frontmatter(stage, revision=3)
    mutate_stage_map_entry(plan, "S01", revision=3)
    with plan.open("a", encoding="utf-8") as output:
        output.write("\n## Blocker\n\nS01 exhausted revision budget; review findings remain actionable.\n")
    review = system.workspace / "1_orchestrator/e2e/reviews/01.md"
    write_technical_review(review, "S01", 3, "REVISE", "Validation remains incomplete.")
    validate_fixture_state(plan, "S01", stage, review, expected_plan=PlanFrontmatter("blocked", "S01"), expected_stage_status="BLOCKED", expected_artifact_status="REVIEW", expected_review_status="REVISE")
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    assert parse_plan_frontmatter(plan) == PlanFrontmatter("planning", "S01")
    assert parse_stage_map_entry(plan, "S01").status == "PLANNING"
    system.assert_task_sequence(messages, [])
print("revision resume E2E passed")
