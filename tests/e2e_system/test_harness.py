#!/usr/bin/env python3

import unittest
from unittest.mock import Mock, patch

from harness import SystemWorkspace


class HarnessTimingTests(unittest.TestCase):
    def test_measure_records_monotonic_duration_and_preserves_exception(self):
        system = SystemWorkspace.__new__(SystemWorkspace)
        system.timings = {}
        system.session_ids = []
        system.task_call_count = 0
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
        system.task_agent_names = ["orchestrator-stage-planner", "orchestrator-stage-reviewer"]
        result = system.timing_result()
        self.assertEqual(result["sessions_created"], 2)
        self.assertEqual(result["task_calls"], 2)
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


if __name__ == "__main__":
    unittest.main()
