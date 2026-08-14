#!/usr/bin/env python3

import unittest
from typing import Any
from unittest.mock import Mock, patch

from harness import SystemWorkspace, assert_task_sequence, failed_task_calls, incomplete_task_calls, successful_task_calls, task_trace


class HarnessTimingTests(unittest.TestCase):
    def test_measure_records_monotonic_duration_and_preserves_exception(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.timings = {}
        system.session_ids = []
        system.task_call_count = 0
        system.successful_task_call_count = 0
        system.failed_task_call_count = 0
        system.incomplete_task_call_count = 0
        system.task_agent_names = []
        failure = RuntimeError("test-only failure")
        with patch("harness.time.monotonic", side_effect=[10.0, 12.5]):
            with self.assertRaisesRegex(RuntimeError, "test-only failure") as raised:
                with system._measure("failure_path"):
                    raise failure
        self.assertIs(raised.exception, failure)
        self.assertEqual(system.timings, {"failure_path": [2.5]})
        self.assertEqual(system.timing_result()["durations_seconds"], {"failure_path": [2.5]})

    def test_timing_result_copies_aggregate_ready_data(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.timings = {"fixture_setup": [1.0], "prompt_to_idle": [2.0, 3.0]}
        system.session_ids = ["session-1", "session-2"]
        system.task_call_count = 2
        system.successful_task_call_count = 2
        system.failed_task_call_count = 0
        system.incomplete_task_call_count = 0
        system.task_agent_names = ["orchestrator-stage-planner", "orchestrator-stage-reviewer"]
        result = system.timing_result()
        self.assertEqual(result["sessions_created"], 2)
        self.assertEqual(result["task_calls"], 2)
        self.assertEqual(result["successful_task_calls"], 2)
        self.assertEqual(result["failed_task_calls"], 0)
        self.assertEqual(result["incomplete_task_calls"], 0)
        self.assertEqual(result["task_agent_names"], ["orchestrator-stage-planner", "orchestrator-stage-reviewer"])
        self.assertEqual(result["durations_seconds"]["prompt_to_idle"], [2.0, 3.0])
        result["durations_seconds"]["prompt_to_idle"].append(4.0)
        self.assertEqual(system.timings["prompt_to_idle"], [2.0, 3.0])

    def test_close_is_idempotent(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.timings = {}
        system._test_started_at = 0.0
        system._closed = False
        system._cleanup_started_at = None
        system.process = None
        system.temporary = Mock()
        system.close()
        system.close()
        self.assertEqual(len(system.timings["cleanup"]), 1)
        self.assertEqual(len(system.timings["test_case_total"]), 1)
        system.temporary.cleanup.assert_called_once_with()

    def test_close_retries_failed_cleanup_without_duplicate_timing(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.timings = {}
        system._test_started_at = 0.0
        system._closed = False
        system._cleanup_started_at = None
        system.process = None
        system.temporary = Mock()
        system.temporary.cleanup.side_effect = [RuntimeError("cleanup failure"), None]
        with self.assertRaisesRegex(RuntimeError, "cleanup failure"):
            system.close()
        self.assertFalse(system._closed)
        self.assertNotIn("cleanup", system.timings)
        self.assertNotIn("test_case_total", system.timings)
        system.close()
        system.close()
        self.assertTrue(system._closed)
        self.assertEqual(len(system.timings["cleanup"]), 1)
        self.assertEqual(len(system.timings["test_case_total"]), 1)
        self.assertEqual(system.temporary.cleanup.call_count, 2)

    def test_repeated_start_fails_before_process_launch(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system._start_attempted = True
        with self.assertRaisesRegex(AssertionError, "may only be called once"):
            system.start()

    def test_enter_preserves_start_exception_when_cleanup_fails(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        failure = RuntimeError("start failure")
        system._start_on_enter = True
        system.start = Mock(side_effect=failure)
        system.close = Mock(side_effect=RuntimeError("cleanup failure"))
        with self.assertRaisesRegex(RuntimeError, "start failure") as raised:
            system.__enter__()
        self.assertIs(raised.exception, failure)

    def test_exit_preserves_body_exception_when_cleanup_fails(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.close = Mock(side_effect=RuntimeError("cleanup failure"))
        failure = RuntimeError("body failure")
        self.assertIsNone(system.__exit__(RuntimeError, failure, None))

    def test_completed_task_is_successful_and_preserves_details(self):
        messages = self._messages("completed", agent_name="orchestrator-stage-reviewer", output="STAGE_REVIEW: PASS", call_id="call-1")
        call = assert_task_sequence(messages, ["orchestrator-stage-reviewer"])[0]
        self.assertEqual(call.call_id, "call-1")
        self.assertEqual(call.order, 0)
        self.assertEqual(call.input, {"subagent_type": "orchestrator-stage-reviewer", "prompt": "review"})
        self.assertEqual(call.output, "STAGE_REVIEW: PASS")
        self.assertEqual(call.compact_result, "STAGE_REVIEW: PASS")

    def test_error_task_is_not_successful_and_error_is_diagnostic(self):
        messages = self._messages("error", error="review failed")
        self.assertEqual(successful_task_calls(messages), [])
        with self.assertRaisesRegex(AssertionError, "review failed"):
            assert_task_sequence(messages, ["orchestrator-stage-reviewer"])

    def test_structured_error_on_completed_task_is_not_successful(self):
        messages = self._messages("completed", output="done")
        messages[0]["parts"][0]["state"]["error"] = {"message": "structured failure"}
        self.assertEqual(successful_task_calls(messages), [])
        with self.assertRaisesRegex(AssertionError, "structured failure"):
            assert_task_sequence(messages, ["orchestrator-stage-planner"])

    def test_pending_running_and_missing_state_are_not_successful(self):
        for status in ("pending", "running", None):
            with self.subTest(status=status):
                messages = self._messages(status)
                self.assertEqual(successful_task_calls(messages), [])
                with self.assertRaisesRegex(AssertionError, "failed_or_incomplete"):
                    assert_task_sequence(messages, ["orchestrator-stage-reviewer"])

    def test_task_without_subagent_type_is_not_valid_delegation(self):
        messages = self._messages("completed", agent_name=None, output="done")
        self.assertEqual(successful_task_calls(messages), [])
        with self.assertRaisesRegex(AssertionError, "agent_name=None"):
            assert_task_sequence(messages, [])

    def test_unknown_subagent_type_is_not_successful(self):
        messages = self._messages("completed", agent_name="unexpected-agent", output="done")
        self.assertEqual(successful_task_calls(messages), [])
        self.assertEqual(incomplete_task_calls(messages), task_trace(messages))
        with self.assertRaisesRegex(AssertionError, "unexpected-agent"):
            assert_task_sequence(messages, ["orchestrator-stage-planner"])

    def test_duplicate_wrong_order_and_unexpected_agent_are_rejected(self):
        planner = self._messages("completed", output="planned")[0]["parts"][0]
        reviewer = self._messages("completed", agent_name="orchestrator-stage-reviewer", output="reviewed")[0]["parts"][0]
        with self.assertRaisesRegex(AssertionError, "task trace mismatch"):
            assert_task_sequence([{"parts": [planner, planner]}], ["orchestrator-stage-planner"])
        with self.assertRaisesRegex(AssertionError, "task trace mismatch"):
            assert_task_sequence([{"parts": [reviewer, planner]}], ["orchestrator-stage-planner", "orchestrator-stage-reviewer"])
        with self.assertRaisesRegex(AssertionError, "task trace mismatch"):
            assert_task_sequence([{"parts": [reviewer]}], ["orchestrator-stage-planner"])

    def test_attempt_and_success_counts_are_separate(self):
        completed = self._messages("completed", output="done")[0]["parts"][0]
        pending = self._messages("pending")[0]["parts"][0]
        messages = [{"parts": [completed, pending]}]
        self.assertEqual(len(task_trace(messages)), 2)
        self.assertEqual(len(successful_task_calls(messages)), 1)
        self.assertEqual(len(failed_task_calls(messages)), 0)
        self.assertEqual(len(incomplete_task_calls(messages)), 1)

    def test_failed_and_incomplete_calls_are_classified_separately(self):
        failed = self._messages("error", error="failed")[0]["parts"][0]
        running = self._messages("running")[0]["parts"][0]
        messages = [{"parts": [failed, running]}]
        self.assertEqual(len(failed_task_calls(messages)), 1)
        self.assertEqual(len(incomplete_task_calls(messages)), 1)

    def test_wait_for_idle_does_not_return_for_running_task(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.base_url = "http://test"
        running_messages = self._messages("running")
        running_messages[0]["info"] = {"role": "assistant", "time": {"completed": 1}}
        completed_messages = self._messages("completed", output="done")
        completed_messages[0]["info"] = {"role": "assistant", "time": {"completed": 2}}
        responses = iter([{}, {"session-1": {"type": "idle"}}, running_messages, {}, {"session-1": {"type": "idle"}}, completed_messages])
        requests = []
        def request(*args, **_kwargs):
            requests.append(args[2])
            return next(responses)
        with patch("harness.request_json", side_effect=request), patch("harness.time.monotonic", side_effect=[0, 0, 0]), patch("harness.time.sleep"):
            system._wait_for_idle("session-1")
        self.assertEqual(requests.count("/session/session-1/message"), 2)

    def test_run_step_preserves_execution_error_when_post_failure_snapshot_fails(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.workspace = Mock()
        system.expected_request_target = Mock()
        failure = RuntimeError("execution failed")
        system._run_step = Mock(side_effect=failure)
        with patch("harness.capture_workspace_snapshot", side_effect=[Mock(), OSError("snapshot failed")]):
            with self.assertRaisesRegex(RuntimeError, "execution failed") as raised:
                system.run_step("prompt")
        self.assertIs(raised.exception, failure)
        self.assertIn("snapshot failed", raised.exception.__notes__)

    @staticmethod
    def _messages(status: str | None, agent_name: str | None = "orchestrator-stage-planner", output: str | None = None, error: str | None = None, call_id: str = "call-0") -> list[dict[str, Any]]:
        part: dict[str, Any] = {"type": "tool", "tool": "task", "callID": call_id}
        if status is not None:
            task_input = {"prompt": "review"}
            if agent_name is not None:
                task_input["subagent_type"] = agent_name
            state = {"status": status, "input": task_input}
            if output is not None:
                state["output"] = output
            if error is not None:
                state["error"] = error
            part["state"] = state
        return [{"parts": [part]}]


if __name__ == "__main__":
    unittest.main()
