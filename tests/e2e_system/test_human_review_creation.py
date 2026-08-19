#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, parse_human_review, validate_fixture_state


with SystemWorkspace() as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract")], "S01", "human-reviewing")
    write_passed_stage(system.workspace, 1, "Value contract")
    validate_fixture_state(plan, "S01", system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md", system.workspace / "1_orchestrator/e2e/reviews/01.md", expected_plan=PlanFrontmatter("human-reviewing", "S01"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md")
    human_review = system.workspace / "1_orchestrator/e2e/stages/01-value-contract.human-review.md"
    assert human_review.is_file(), (system.task_agents(messages), messages)
    content = human_review.read_text(encoding="utf-8")
    state = parse_human_review(human_review)
    assert (state.stage_id, state.status, state.revision, state.source_revision) == ("S01", "REVIEW", 1, 1), state
    assert "## Что я получу после этапа" in content, content
    system.assert_task_sequence(messages, ["orchestrator-stage-planner"])
timing = system.timing_result()
assert {"fixture_setup", "environment_setup", "process_startup_to_health", "agent_inventory_loading", "prompt_to_idle", "prompt_or_answer_to_idle", "cleanup", "test_case_total"}.issubset(timing["durations_seconds"]), timing
assert timing["sessions_created"] == 1 and timing["task_calls"] == 1 and timing["successful_task_calls"] == 1 and timing["task_agent_names"] == ["orchestrator-stage-planner"], (timing, messages)
print("human review creation E2E passed")
