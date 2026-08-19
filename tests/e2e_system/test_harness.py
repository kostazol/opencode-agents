#!/usr/bin/env python3

import json
import gc
import os
from pathlib import Path
import tempfile
import unittest
from typing import Any
from unittest.mock import Mock, patch

from harness import DURATION_METRICS, SessionEventWatcher, SystemWorkspace, _decode_sse_data, _new_assistant_turn_state, _session_event_kind, assert_task_sequence, failed_task_calls, incomplete_task_calls, successful_task_calls, task_trace


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

    def test_telemetry_result_has_machine_readable_metrics_and_counts(self):
        system = self._telemetry_system()
        system.timings = {"fixture_setup": [1.0], "subagent": [1.25]}
        system.duration_unavailable["subagent"] = 1
        system.session_ids = ["session-1"]
        system.serve_startup_count = 1
        system.primary_execution_count = 2
        system.task_call_count = 2
        system.successful_task_call_count = 1
        system.incomplete_task_call_count = 1
        system.task_agent_names = ["orchestrator-stage-planner"]
        result = system.telemetry_result()
        self.assertEqual(set(result["durations_seconds"]), set(DURATION_METRICS))
        self.assertEqual(result["counts"]["primary_executions"], 2)
        self.assertEqual(result["durations_seconds"]["subagent"], {"values": [1.25], "unavailable": 1})
        self.assertEqual(result["ordered_agents"], ["orchestrator-stage-planner"])

    def test_telemetry_is_atomically_written_outside_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            system = self._telemetry_system()
            system._telemetry_path = Path(temporary) / "telemetry.json"
            system._write_telemetry()
            payload = json.loads(system._telemetry_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(list(Path(temporary).glob("*.tmp")), [])

    def test_multiple_workspaces_accumulate_process_telemetry(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "telemetry.json"
            first = self._telemetry_system()
            second = self._telemetry_system()
            for system, session_id in ((first, "session-1"), (second, "session-2")):
                system._telemetry_path = path
                system.serve_startup_count = 1
                system.session_ids = [session_id]
                system.primary_execution_count = 1
                system.timings = {name: [0.1] for name in ("fixture_setup", "environment_setup", "process_startup_to_health", "agent_inventory_loading", "prompt_to_idle", "polling", "cleanup", "total")}
                system._write_telemetry()
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["counts"]["serve_startups"], 2)
            self.assertEqual(payload["counts"]["sessions"], 2)
            self.assertEqual(payload["durations_seconds"]["total"]["values"], [0.1, 0.1])

    def test_sequential_collected_workspaces_keep_distinct_telemetry(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "telemetry.json"
            for index in range(10):
                system = self._telemetry_system()
                system._telemetry_path = path
                system.serve_startup_count = 1
                system.session_ids = [f"session-{index}"]
                system.primary_execution_count = 1
                system._write_telemetry()
                del system
                gc.collect()
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["counts"]["serve_startups"], 10)
            self.assertEqual(payload["counts"]["sessions"], 10)
            self.assertEqual(payload["status"], "partial")

    def test_fixture_setup_failure_writes_partial_telemetry(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "telemetry.json"
            with patch.dict(os.environ, {"ORCHESTRATOR_E2E_TELEMETRY_PATH": str(path)}), patch.object(SystemWorkspace, "_write_fixture", side_effect=RuntimeError("fixture failure")):
                with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                    SystemWorkspace(start_on_enter=False)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "partial")
            self.assertEqual(len(payload["durations_seconds"]["fixture_setup"]["values"]), 1)
            self.assertEqual(len(payload["durations_seconds"]["total"]["values"]), 1)

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
        self.assertIn("workspace cleanup failed: cleanup failure", failure.__notes__[0])

    def test_cleanup_failure_writes_partial_telemetry_before_reraising(self):
        with tempfile.TemporaryDirectory() as temporary:
            system = self._telemetry_system()
            system._closed = False
            system._cleanup_started_at = None
            system._test_started_at = 0.0
            system.process = None
            system.temporary = Mock()
            system.temporary.cleanup.side_effect = RuntimeError("cleanup failure")
            system._telemetry_path = Path(temporary) / "telemetry.json"
            with self.assertRaisesRegex(RuntimeError, "cleanup failure"):
                system.close()
            payload = json.loads(system._telemetry_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "partial")
            self.assertEqual(payload["durations_seconds"]["cleanup"]["unavailable"], 1)

    def test_completed_task_is_successful_and_preserves_details(self):
        compact = self._valid_result("orchestrator-stage-reviewer")
        output = self._wrapped(compact)
        messages = self._messages("completed", agent_name="orchestrator-stage-reviewer", output=output, call_id="call-1")
        call = assert_task_sequence(messages, ["orchestrator-stage-reviewer"])[0]
        self.assertEqual(call.call_id, "call-1")
        self.assertEqual(call.order, 0)
        self.assertEqual(call.input, {"subagent_type": "orchestrator-stage-reviewer", "prompt": "review"})
        self.assertTrue(call.execution_completed)
        self.assertEqual(call.started_at_ms, 1000)
        self.assertEqual(call.ended_at_ms, 2000)
        self.assertEqual(call.output, output)
        self.assertEqual(call.raw_output, output)
        self.assertIsNone(call.execution_error)
        self.assertEqual(call.compact_result, compact)
        self.assertTrue(call.result_valid)
        self.assertIsNone(call.parse_diagnostic)
        self.assertEqual(call.duration_seconds, 1.0)

    def test_subagent_duration_rejects_missing_invalid_and_unordered_tool_times(self):
        cases = (
            None,
            {},
            {"start": True, "end": 2000},
            {"start": 1000.0, "end": 2000},
            {"start": 2000, "end": 1000},
            {"start": -2000, "end": -1000},
            {"start": 2**54, "end": 2**54 + 1000},
            {"start": 1000, "end": "2000"},
        )
        for task_time in cases:
            with self.subTest(task_time=task_time):
                messages = self._messages("completed", output=self._wrapped(self._valid_result("orchestrator-stage-planner")))
                if task_time is None:
                    messages[0]["parts"][0]["state"].pop("time")
                else:
                    messages[0]["parts"][0]["state"]["time"] = task_time
                self.assertIsNone(task_trace(messages)[0].duration_seconds)

    def test_subagent_duration_accepts_observed_integer_milliseconds(self):
        messages = self._messages("completed", output=self._wrapped(self._valid_result("orchestrator-stage-planner")))
        messages[0]["parts"][0]["state"]["time"] = {"start": 1001, "end": 2251}
        self.assertEqual(task_trace(messages)[0].duration_seconds, 1.25)

    def test_direct_compact_result_without_tool_wrapper_is_rejected(self):
        compact = self._valid_result("orchestrator-discovery")
        call = task_trace(self._messages("completed", agent_name="orchestrator-discovery", output=compact))[0]
        self.assertFalse(call.successful)
        self.assertIsNone(call.compact_result)
        self.assertEqual(call.parse_diagnostic, "malformed task result wrapper")

    def test_correct_results_for_each_role_are_valid(self):
        for agent_name in ("orchestrator-discovery", "orchestrator-stage-planner", "orchestrator-stage-reviewer"):
            with self.subTest(agent_name=agent_name):
                output = self._wrapped(self._valid_result(agent_name))
                call = task_trace(self._messages("completed", agent_name=agent_name, output=output))[0]
                self.assertTrue(call.successful, call)

    def test_role_result_paths_reject_wrong_artifact_families(self):
        cases = (
            ("orchestrator-discovery", self._valid_result("orchestrator-discovery").replace("1_orchestrator/e2e/discovery.md", "1_orchestrator/e2e/stages/discovery.md")),
            ("orchestrator-stage-planner", self._valid_result("orchestrator-stage-planner").replace("/stages/", "/reviews/")),
            ("orchestrator-stage-reviewer", self._valid_result("orchestrator-stage-reviewer").replace("/reviews/", "/stages/")),
        )
        for agent_name, compact in cases:
            with self.subTest(agent_name=agent_name):
                call = task_trace(self._messages("completed", agent_name=agent_name, output=self._wrapped(compact)))[0]
                self.assertFalse(call.result_valid, call)

    def test_role_result_paths_reject_parent_traversal_request(self):
        compact = self._valid_result("orchestrator-discovery").replace("1_orchestrator/e2e/", "1_orchestrator/../")
        call = task_trace(self._messages("completed", agent_name="orchestrator-discovery", output=self._wrapped(compact)))[0]
        self.assertFalse(call.result_valid, call)

    def test_role_result_paths_require_internal_stage_and_request_identity(self):
        cases = (
            ("orchestrator-discovery", self._valid_result("orchestrator-discovery").replace("1_orchestrator/e2e/plan.md", "1_orchestrator/other/plan.md")),
            ("orchestrator-stage-planner", self._valid_result("orchestrator-stage-planner").replace("stages/01-", "stages/02-")),
            ("orchestrator-stage-reviewer", self._valid_result("orchestrator-stage-reviewer").replace("reviews/01.md", "reviews/02.md")),
        )
        for agent_name, compact in cases:
            with self.subTest(agent_name=agent_name):
                call = task_trace(self._messages("completed", agent_name=agent_name, output=self._wrapped(compact)))[0]
                self.assertFalse(call.result_valid, call)

    def test_malformed_completed_exact_sequence_is_rejected(self):
        compact = self._valid_result("orchestrator-stage-planner")
        messages = self._messages("completed", output=f"prose\n{self._wrapped(compact)}")
        self.assertEqual(successful_task_calls(messages), [])
        with self.assertRaisesRegex(AssertionError, "malformed task result wrapper"):
            assert_task_sequence(messages, ["orchestrator-stage-planner"])

    def test_execution_error_rejects_valid_role_result(self):
        messages = self._messages("completed", output=self._wrapped(self._valid_result("orchestrator-stage-planner")), error="execution failed")
        call = task_trace(messages)[0]
        self.assertTrue(call.result_valid)
        self.assertFalse(call.successful)
        self.assertEqual(failed_task_calls(messages), [call])

    def test_role_result_validation_rejects_malformed_shapes(self):
        valid = self._valid_result("orchestrator-stage-reviewer")
        cases = {
            "missing": "\n".join(valid.splitlines()[:-1]),
            "prose": f"preface\n{valid}",
            "duplicate": valid.replace("SUMMARY: reviewed", "FINDINGS: 0\nSUMMARY: reviewed"),
            "unknown label": valid.replace("REVIEW: ", "OUTPUT: "),
            "bad status": valid.replace("STAGE_REVIEW: PASS", "STAGE_REVIEW: DONE"),
            "bad stage": valid.replace("STAGE: S01", "STAGE: 01"),
            "bad revision": valid.replace("REVISION: 1", "REVISION: 0"),
            "bad findings": valid.replace("FINDINGS: 0", "FINDINGS: -1"),
            "empty path": valid.replace("REVIEW: 1_orchestrator/e2e/reviews/01.md", "REVIEW: "),
            "empty summary": valid.replace("SUMMARY: reviewed", "SUMMARY: "),
        }
        for name, output in cases.items():
            with self.subTest(name=name):
                call = task_trace(self._messages("completed", agent_name="orchestrator-stage-reviewer", output=self._wrapped(output)))[0]
                self.assertFalse(call.result_valid)
                self.assertIsNotNone(call.parse_diagnostic)

    def test_non_string_missing_and_malformed_wrapper_outputs_are_rejected(self):
        outputs = [None, {"result": "value"}, "<task id=\"x\" state=\"completed\">\n<task_result>\ninvalid\n</task_result>\n</task> trailing"]
        for output in outputs:
            with self.subTest(output=output):
                messages = self._messages("completed", output=output)
                call = task_trace(messages)[0]
                self.assertFalse(call.result_valid)
                self.assertIsNotNone(call.parse_diagnostic)
                self.assertEqual(call.raw_output, output)

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
        planner = self._messages("completed", output=self._wrapped(self._valid_result("orchestrator-stage-planner")))[0]["parts"][0]
        reviewer = self._messages("completed", agent_name="orchestrator-stage-reviewer", output=self._wrapped(self._valid_result("orchestrator-stage-reviewer")))[0]["parts"][0]
        with self.assertRaisesRegex(AssertionError, "task trace mismatch"):
            assert_task_sequence([{"parts": [planner, planner]}], ["orchestrator-stage-planner"])
        with self.assertRaisesRegex(AssertionError, "task trace mismatch"):
            assert_task_sequence([{"parts": [reviewer, planner]}], ["orchestrator-stage-planner", "orchestrator-stage-reviewer"])
        with self.assertRaisesRegex(AssertionError, "task trace mismatch"):
            assert_task_sequence([{"parts": [reviewer]}], ["orchestrator-stage-planner"])

    def test_attempt_and_success_counts_are_separate(self):
        completed = self._messages("completed", output=self._wrapped(self._valid_result("orchestrator-stage-planner")))[0]["parts"][0]
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

    def test_old_running_task_does_not_block_new_completed_turn(self):
        old = self._assistant_message("old", "completed", "running")
        new = self._assistant_message("new", "completed")
        terminal, diagnostic = _new_assistant_turn_state([old, new], frozenset({"old"}))
        self.assertTrue(terminal, diagnostic)

    def test_old_completed_turn_cannot_satisfy_new_boundary(self):
        old = self._assistant_message("old", "completed")
        terminal, diagnostic = _new_assistant_turn_state([old], frozenset({"old"}))
        self.assertFalse(terminal)
        self.assertIn("no new assistant turn", diagnostic)

    def test_incomplete_question_turn_can_complete_after_reply_boundary(self):
        completed = self._assistant_message("question-turn", "completed")
        terminal, diagnostic = _new_assistant_turn_state([completed], {"question-turn": False})
        self.assertTrue(terminal, diagnostic)

    def test_running_new_task_blocks_until_same_turn_is_terminal(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.base_url = "http://test"
        running_messages = [self._assistant_message("new", "completed", "running")]
        completed_messages = [self._assistant_message("new", "completed", "completed", self._valid_result("orchestrator-stage-planner"))]
        responses = iter([{}, {"session-1": {"type": "idle"}}, running_messages, {}, {"session-1": {"type": "idle"}}, completed_messages])
        requests = []
        def request(*args, **_kwargs):
            requests.append(args[2])
            return next(responses)
        event_watcher = self._event_watcher()
        with patch("harness.request_json", side_effect=request), patch("harness.time.monotonic", side_effect=[0, 0, 0]), patch("harness.time.sleep"):
            system._wait_for_idle("session-1", frozenset(), event_watcher, 0)
        self.assertEqual(requests.count("/session/session-1/message"), 2)

    def test_error_task_is_terminal_and_remains_traceable(self):
        message = self._assistant_message("new", "completed", "error", error="failed")
        terminal, diagnostic = _new_assistant_turn_state([message], frozenset())
        self.assertTrue(terminal, diagnostic)
        self.assertEqual(len(failed_task_calls([message])), 1)

    def test_wait_fallback_requires_explicit_idle(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.base_url = "http://test"
        completed = [self._assistant_message("new", "completed")]
        responses = iter([RuntimeError("POST failed with HTTP 503: Session wait is not available yet"), {"session-1": {"type": "busy"}}, completed, {"session-1": {"type": "idle"}}, completed])
        def request(*_args, **_kwargs):
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response
        event_watcher = self._event_watcher()
        with patch("harness.request_json", side_effect=request), patch("harness.time.monotonic", side_effect=[0, 0, 0]), patch("harness.time.sleep"):
            system._wait_for_idle("session-1", frozenset(), event_watcher, 0)

    def test_timed_out_wait_checks_explicit_idle_and_terminal_turn_same_iteration(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.base_url = "http://test"
        completed = [self._assistant_message("new", "completed")]
        responses = iter([TimeoutError(), {"session-1": {"type": "idle"}}, completed])
        requests = []
        def request(*args, **_kwargs):
            requests.append(args[2])
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response
        event_watcher = self._event_watcher()
        with patch("harness.request_json", side_effect=request), patch("harness.time.monotonic", side_effect=[0, 0]):
            system._wait_for_idle("session-1", frozenset(), event_watcher, 0)
        self.assertEqual(requests, ["/api/session/session-1/wait", "/session/status", "/session/session-1/message"])

    def test_explicit_busy_vetoes_idle_event_until_status_is_terminal(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.base_url = "http://test"
        completed = [self._assistant_message("new", "completed")]
        responses = iter([RuntimeError("POST failed with HTTP 503: Session wait is not available yet"), {"session-1": {"type": "busy"}}, completed, {"session-1": {"type": "idle"}}, completed])
        requests = []
        def request(*args, **_kwargs):
            requests.append(args[2])
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response
        event_watcher = self._event_watcher(idle=True)
        with patch("harness.request_json", side_effect=request), patch("harness.time.monotonic", side_effect=[0, 0, 0]), patch("harness.time.sleep"):
            system._wait_for_idle("session-1", frozenset(), event_watcher, 0)
        self.assertEqual(requests.count("/session/status"), 2)
        self.assertEqual(requests.count("/session/session-1/message"), 2)

    def test_wait_timeout_reports_status_assistant_and_task_diagnostics(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.base_url = "http://test"
        running = [self._assistant_message("new", None, "running")]
        responses = iter([{}, {"session-1": {"type": "busy"}}, running])
        event_watcher = self._event_watcher()
        with patch("harness.TIMEOUT_SECONDS", 1), patch("harness.request_json", side_effect=lambda *_args, **_kwargs: next(responses)), patch("harness.time.monotonic", side_effect=[0, 0, 2]), patch("harness.time.sleep"):
            with self.assertRaisesRegex(AssertionError, "session session-1 did not become idle: status=.*assistant_id='new'.*tasks="):
                system._wait_for_idle("session-1", frozenset(), event_watcher, 0)

    def test_missing_status_without_wait_or_idle_event_does_not_complete(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.base_url = "http://test"
        completed = [self._assistant_message("new", "completed")]
        responses = iter([RuntimeError("POST failed with HTTP 503: Session wait is not available yet"), {}, completed])
        def request(*_args, **_kwargs):
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response
        event_watcher = self._event_watcher()
        with patch("harness.TIMEOUT_SECONDS", 1), patch("harness.request_json", side_effect=request), patch("harness.time.monotonic", side_effect=[0, 0, 2]):
            with self.assertRaisesRegex(AssertionError, "status=None.*event_idle=False"):
                system._wait_for_idle("session-1", frozenset(), event_watcher, 0)

    def test_idle_event_completes_when_status_omits_session(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.base_url = "http://test"
        completed = [self._assistant_message("new", "completed")]
        responses = iter([RuntimeError("POST failed with HTTP 503: Session wait is not available yet"), {}, completed])
        def request(*_args, **_kwargs):
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response
        event_watcher = self._event_watcher(idle=True)
        with patch("harness.request_json", side_effect=request), patch("harness.time.monotonic", side_effect=[0, 0]):
            system._wait_for_idle("session-1", frozenset(), event_watcher, 0)

    def test_sse_parsing_and_session_event_classification(self):
        connected = _decode_sse_data(['data: {"type":"server.connected","properties":{}}'])
        idle = _decode_sse_data(['data: {"type":"session.status",', 'data: "properties":{"sessionID":"session-1","status":{"type":"idle"}}}'])
        deprecated = {"type": "session.idle", "properties": {"sessionID": "session-1"}}
        assert connected is not None
        assert idle is not None
        self.assertEqual(_session_event_kind(connected, "session-1"), "connected")
        self.assertEqual(_session_event_kind(idle, "session-1"), "idle")
        self.assertEqual(_session_event_kind(deprecated, "session-1"), "idle")
        self.assertIsNone(_session_event_kind(idle, "session-2"))
        self.assertIsNone(_decode_sse_data(["data: invalid-json"]))

    def test_event_watcher_readiness_idle_and_cleanup(self):
        response = self._EventResponse([b'data: {"type":"server.connected","properties":{}}\n', b'\n', b'data: {"type":"session.status","properties":{"sessionID":"session-1","status":{"type":"idle"}}}\n', b'\n'])
        with patch("harness.urlopen", return_value=response):
            with SessionEventWatcher("http://test", "session-1") as watcher:
                self.assertTrue(watcher.has_idle_after(0))
        self.assertTrue(response.closed)

    def test_event_watcher_requires_server_connected_readiness(self):
        response = self._EventResponse([b'data: invalid\n', b'\n'])
        with patch("harness.urlopen", return_value=response):
            with self.assertRaisesRegex(AssertionError, "failed before readiness"):
                with SessionEventWatcher("http://test", "session-1"):
                    self.fail("watcher entered without readiness")
        self.assertTrue(response.closed)

    def test_event_watcher_cleanup_preserves_original_exception(self):
        watcher = SessionEventWatcher("http://test", "session-1")
        watcher.close = Mock(side_effect=RuntimeError("close failed"))
        failure = RuntimeError("body failed")
        self.assertFalse(watcher.__exit__(RuntimeError, failure, None))
        self.assertIn("close failed", failure.__notes__[0])

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
    def _messages(status: str | None, agent_name: str | None = "orchestrator-stage-planner", output: Any = None, error: str | None = None, call_id: str = "call-0") -> list[dict[str, Any]]:
        part: dict[str, Any] = {"type": "tool", "tool": "task", "callID": call_id}
        if status is not None:
            task_input = {"prompt": "review"}
            if agent_name is not None:
                task_input["subagent_type"] = agent_name
            state = {"status": status, "input": task_input, "time": {"start": 1000, "end": 2000}}
            if output is not None:
                state["output"] = output
            if error is not None:
                state["error"] = error
            part["state"] = state
        return [{"parts": [part]}]

    @staticmethod
    def _telemetry_system() -> SystemWorkspace:
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.timings = {}
        system.duration_unavailable = {name: 0 for name in DURATION_METRICS}
        system._telemetry_path = None
        system._telemetry_partial = False
        system.session_ids = []
        system.serve_startup_count = 0
        system.primary_execution_count = 0
        system.task_call_count = 0
        system.successful_task_call_count = 0
        system.failed_task_call_count = 0
        system.incomplete_task_call_count = 0
        system.task_agent_names = []
        return system

    @staticmethod
    def _event_watcher(idle: bool = False) -> Mock:
        watcher = Mock()
        watcher.has_idle_after.return_value = idle
        watcher.diagnostic.return_value = f"event_idle_count={1 if idle else 0}; event_boundary=0; event_error=None"
        return watcher

    @classmethod
    def _assistant_message(cls, message_id: str, completed: str | None, task_status: str | None = None, output: str | None = None, error: str | None = None) -> dict[str, Any]:
        message: dict[str, Any] = cls._messages(task_status, output=output, error=error)[0] if task_status is not None else {"parts": []}
        message["info"] = {"id": message_id, "role": "assistant", "time": {}}
        if completed is not None:
            message["info"]["time"]["completed"] = completed
        return message

    @staticmethod
    def _wrapped(compact: str) -> str:
        return f'<task id="task-1" state="completed">\n<task_result>\n{compact}\n</task_result>\n</task>'

    @staticmethod
    def _valid_result(agent_name: str) -> str:
        if agent_name == "orchestrator-discovery":
            return "DISCOVERY: QUESTIONS\nARTIFACT: 1_orchestrator/e2e/discovery.md\nQUESTIONS: 1_orchestrator/e2e/questions.md\nPLAN: 1_orchestrator/e2e/plan.md\nSUMMARY: discovered"
        if agent_name == "orchestrator-stage-planner":
            return "STAGE_PLAN: REVIEW\nSTAGE: S01\nREVISION: 1\nARTIFACT: 1_orchestrator/e2e/stages/01-value.md\nSUMMARY: planned"
        return "STAGE_REVIEW: PASS\nSTAGE: S01\nREVISION: 1\nREVIEW: 1_orchestrator/e2e/reviews/01.md\nFINDINGS: 0\nSUMMARY: reviewed"

    class _EventResponse:
        def __init__(self, lines: list[bytes]):
            self.lines = lines
            self.closed = False

        def __iter__(self):
            return iter(self.lines)

        def close(self):
            self.closed = True


if __name__ == "__main__":
    unittest.main()
