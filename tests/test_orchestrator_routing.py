from copy import deepcopy
import unittest

from orchestrator_core.controller import apply_event, create_state, reserve_next
from orchestrator_core.protocol import ProtocolError
from orchestrator_core.render import render_plan
from tests.orchestrator_fixture import analysis_fixture, advance_to_stage_planning, event, finding


class ControllerTests(unittest.TestCase):
    def test_full_pure_journey(self):
        state, analysis = advance_to_stage_planning()
        state, action = reserve_next(state, analysis)
        self.assertEqual((action["action"], action["revision"]), ("PLAN_STAGE", 1))
        state, _ = apply_event(state, event(action, "stage_plan_result", status="REVIEW", revision=1), analysis)
        state, action = reserve_next(state, analysis)
        self.assertEqual(action["action"], "REVIEW_STAGE")
        state, _ = apply_event(state, event(action, "stage_review_result", status="PASS", revision=1), analysis)
        state, action = reserve_next(state, analysis)
        self.assertEqual(action["action"], "PLAN_HUMAN_REVIEW")
        state, _ = apply_event(state, event(action, "human_plan_result", status="REVIEW", revision=1), analysis)
        state, action = reserve_next(state, analysis)
        state, _ = apply_event(state, event(action, "human_review_result", status="PASS", revision=1), analysis)
        state, action = reserve_next(state, analysis)
        self.assertEqual(action["action"], "APPROVE_PLAN")
        state, result = apply_event(state, event(action, "plan_decision", decision="APPROVE"), analysis)
        self.assertEqual(result["status"], "ready")
        state, action = reserve_next(state, analysis)
        self.assertEqual(action["action"], "COMPLETE")
        self.assertIsNone(state["pending"])

    def test_repeated_reserve_returns_same_transition(self):
        state = create_state("sample")
        first_state, first = reserve_next(state)
        second_state, second = reserve_next(first_state)
        self.assertEqual(first_state, second_state)
        self.assertEqual(first, second)

    def test_duplicate_event_is_idempotent_but_conflicting_payload_is_rejected(self):
        state = create_state("sample")
        state, action = reserve_next(state)
        value = event(action, "discovery_result", status="READY_FOR_REVIEW", revision=1)
        applied, first = apply_event(state, value, analysis_fixture())
        repeated, second = apply_event(applied, value, analysis_fixture())
        self.assertEqual(applied, repeated)
        self.assertEqual(first, second)
        conflict = deepcopy(value)
        conflict["payload"]["status"] = "QUESTIONS"
        with self.assertRaisesRegex(ProtocolError, "already applied with different"):
            apply_event(applied, conflict, analysis_fixture())

    def test_expected_revision_rejects_concurrent_advance(self):
        state = create_state("sample")
        with self.assertRaisesRegex(ProtocolError, "state revision conflict"):
            reserve_next(state, expected_state_revision=1)

    def test_revise_reserves_next_monotonic_revision(self):
        state, analysis = advance_to_stage_planning()
        state, action = reserve_next(state, analysis)
        state, _ = apply_event(state, event(action, "stage_plan_result", status="REVIEW", revision=1), analysis)
        state, action = reserve_next(state, analysis)
        state, _ = apply_event(state, event(action, "stage_review_result", status="REVISE", revision=1, findings=finding()), analysis)
        state, action = reserve_next(state, analysis)
        self.assertEqual((action["action"], action["revision"]), ("PLAN_STAGE", 2))

    def test_task_failure_blocks_and_retry_reuses_reserved_revision(self):
        state, analysis = advance_to_stage_planning()
        state, action = reserve_next(state, analysis)
        state, result = apply_event(
            state,
            event(action, "task_failure", reason="timeout", detail="planner deadline", retryable=True),
            analysis,
        )
        self.assertEqual(result["status"], "blocked")
        state, resolve = reserve_next(state, analysis)
        state, _ = apply_event(state, event(resolve, "blocker_resolution", decision="RETRY"), analysis)
        state, retried = reserve_next(state, analysis)
        self.assertEqual((retried["action"], retried["revision"]), ("PLAN_STAGE", 1))

    def test_illegal_event_type_is_rejected(self):
        state = create_state("sample")
        state, action = reserve_next(state)
        with self.assertRaisesRegex(ProtocolError, "expected discovery_result"):
            apply_event(state, event(action, "stage_plan_result", status="REVIEW", revision=1))

    def test_plan_render_is_stable_and_contains_traceability(self):
        state, analysis = advance_to_stage_planning()
        rendered = render_plan(state, analysis)
        self.assertIn("schema_version: 1", rendered)
        self.assertIn("## Traceability", rendered)
        self.assertIn("`REQ-001` → `S01`", rendered)


if __name__ == "__main__":
    unittest.main()
