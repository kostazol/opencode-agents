#!/usr/bin/env python3

from harness import SystemWorkspace


with SystemWorkspace() as system:
    target = system.workspace / "1_orchestrator/e2e"
    target.mkdir(parents=True)
    (target / "plan.md").write_text("---\nstatus: waiting-answers\ncurrent_stage: none\n---\n\n# Plan\n", encoding="utf-8")
    (target / "questions.md").write_text("---\nstatus: pending\nrevision: 1\n---\n\n# Questions\n\n## Q1 — Output format\n\nWhich output format should the API return?\n\n### Options\n- JSON — stable structured contract.\n- Plain text — smaller human-readable response.\n\n### Recommendation\nJSON.\n\n### Answer\npending\n", encoding="utf-8")
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md", ["JSON"])
    questions = (target / "questions.md").read_text(encoding="utf-8")
    plan = (target / "plan.md").read_text(encoding="utf-8")
    assert "status: answered" in questions
    assert "JSON" in questions
    assert "status: discovery" in plan
    system.assert_task_sequence(messages, [])
timing = system.timing_result()
assert "prompt_to_question" in timing["durations_seconds"] and "answer_to_idle" in timing["durations_seconds"] and "prompt_or_answer_to_idle" in timing["durations_seconds"], timing
assert timing["sessions_created"] == 1 and timing["task_calls"] == 0 and timing["successful_task_calls"] == 0 and timing["task_agent_names"] == [], timing
print("question answers E2E passed")
