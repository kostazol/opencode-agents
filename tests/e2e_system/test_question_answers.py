#!/usr/bin/env python3

from harness import SystemWorkspace
from fixture_validation import PlanFrontmatter, QuestionState, parse_plan_frontmatter, parse_question_state, write_question_state


with SystemWorkspace() as system:
    target = system.workspace / "1_orchestrator/e2e"
    target.mkdir(parents=True)
    (target / "plan.md").write_text("---\nstatus: waiting-answers\ncurrent_stage: none\n---\n\n# Plan\n", encoding="utf-8")
    write_question_state(target / "questions.md", "pending", 1, "# Questions\n\n## Q1 — Output format\n\nWhich output format should the API return?\n\n### Options\n- JSON — stable structured contract.\n- Plain text — smaller human-readable response.\n\n### Recommendation\nJSON.\n\n### Answer\npending")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md", ["JSON"])
    questions = parse_question_state(target / "questions.md")
    plan = parse_plan_frontmatter(target / "plan.md")
    assert questions.status == "answered" and questions.revision == 1, questions
    assert any("JSON" in answer for answer in questions.answers), questions
    assert plan == PlanFrontmatter("discovery", "none"), plan
    system.assert_task_sequence(messages, [])
timing = system.timing_result()
assert "prompt_to_question" in timing["durations_seconds"] and "answer_to_idle" in timing["durations_seconds"] and "prompt_or_answer_to_idle" in timing["durations_seconds"], timing
assert timing["sessions_created"] == 1 and timing["task_calls"] == 0 and timing["successful_task_calls"] == 0 and timing["task_agent_names"] == [], timing
print("question answers E2E passed")
