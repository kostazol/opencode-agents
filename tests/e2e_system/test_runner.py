#!/usr/bin/env python3

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

import run_e2e


class RunnerTests(unittest.TestCase):
    def test_passed_test_missing_telemetry_is_runner_failure(self):
        with self._scripts({"test_pass.py": "print('pass')\n"}, telemetry=False) as root:
            result = run_e2e.run_suite([root / "test_pass.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertTrue(result.runner_error)
            self.assertIn("missing telemetry fixture", result.detail)

    def test_malformed_telemetry_is_runner_failure(self):
        script = "import os\nopen(os.environ['ORCHESTRATOR_E2E_TELEMETRY_PATH'], 'w').write('{')\n"
        with self._scripts({"test_pass.py": script}, telemetry=False) as root:
            result = run_e2e.run_suite([root / "test_pass.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertTrue(result.runner_error)
            self.assertIn("malformed telemetry fixture", result.detail)

    def test_passed_child_partial_telemetry_is_runner_failure(self):
        script = "import json,os\np=os.environ['ORCHESTRATOR_E2E_TELEMETRY_PATH']\nd=json.load(open(p))\nd['status']='partial'\njson.dump(d,open(p,'w'))\n"
        with self._scripts({"test_pass.py": script}) as root:
            result = run_e2e.run_suite([root / "test_pass.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertTrue(result.runner_error)
            self.assertIn("passed child requires complete telemetry", result.detail)

    def test_complete_telemetry_requires_setup_cleanup_and_total_cardinality(self):
        mandatory = ("fixture_setup", "environment_setup", "process_startup_to_health", "agent_inventory_loading", "cleanup", "total")
        for name in mandatory:
            for metric in ({"values": [], "unavailable": 0}, {"values": [0.1, 0.2], "unavailable": 0}, {"values": [0.1], "unavailable": 1}):
                with self.subTest(name=name, metric=metric):
                    payload = self._telemetry_payload()
                    payload["durations_seconds"][name] = metric
                    with self.assertRaisesRegex(ValueError, f"one available {name} duration per serve startup"):
                        run_e2e._validate_telemetry(payload)

    def test_complete_telemetry_requires_session_and_primary_execution(self):
        payload = self._telemetry_payload()
        payload["counts"]["sessions"] = 0
        payload["counts"]["primary_executions"] = 0
        with self.assertRaisesRegex(ValueError, "at least one primary execution per session"):
            run_e2e._validate_telemetry(payload)

    def test_complete_telemetry_requires_phase_cardinality(self):
        cases = (
            ("prompt_to_idle", [], "initial prompt duration"),
            ("answer_to_idle", [0.1], "answer continuations"),
            ("polling", [], "polling duration"),
        )
        for metric, values, diagnostic in cases:
            with self.subTest(metric=metric):
                payload = self._telemetry_payload()
                payload["durations_seconds"][metric]["values"] = values
                with self.assertRaisesRegex(ValueError, diagnostic):
                    run_e2e._validate_telemetry(payload)

        payload = self._telemetry_payload()
        payload["durations_seconds"]["prompt_to_question"]["values"] = [0.1]
        payload["durations_seconds"]["prompt_to_idle"]["values"] = []
        with self.assertRaisesRegex(ValueError, "questions do not match"):
            run_e2e._validate_telemetry(payload)
        payload = self._telemetry_payload()
        payload["durations_seconds"]["prompt_to_idle"]["unavailable"] = 1
        with self.assertRaisesRegex(ValueError, "unavailable prompt_to_idle"):
            run_e2e._validate_telemetry(payload)

    def test_complete_question_telemetry_phase_cardinality_is_valid(self):
        payload = self._telemetry_payload()
        payload["counts"]["primary_executions"] = 2
        payload["durations_seconds"]["prompt_to_idle"]["values"] = []
        payload["durations_seconds"]["prompt_to_question"]["values"] = [0.1]
        payload["durations_seconds"]["answer_to_idle"]["values"] = [0.1]
        payload["durations_seconds"]["polling"]["values"] = [0.1, 0.1]
        run_e2e._validate_telemetry(payload)

    def test_complete_multi_workspace_telemetry_is_valid(self):
        payload = self._telemetry_payload()
        payload["counts"]["serve_startups"] = 2
        payload["counts"]["sessions"] = 2
        payload["counts"]["primary_executions"] = 2
        for name in ("fixture_setup", "environment_setup", "process_startup_to_health", "agent_inventory_loading", "cleanup", "total", "prompt_to_idle", "polling"):
            payload["durations_seconds"][name]["values"] = [0.1, 0.2]
        run_e2e._validate_telemetry(payload)

    def test_telemetry_rejects_invalid_counter_relations(self):
        cases = (
            ({"serve_startups": 0}, "sessions require"),
            ({"sessions": 1, "primary_executions": 0}, "at least one primary execution"),
            ({"sessions": 1, "primary_executions": 1, "serve_startups": 0}, "sessions require"),
            ({"primary_executions": 1, "sessions": 0}, "require a session"),
            ({"task_attempts": 1}, "do not sum"),
            ({"task_attempts": 1, "task_successes": 1}, "ordered_agents count"),
            ({"task_attempts": -1, "task_incomplete": -1}, "count metrics mismatch"),
        )
        for updates, diagnostic in cases:
            with self.subTest(updates=updates):
                payload = self._telemetry_payload()
                payload["counts"].update(updates)
                with self.assertRaisesRegex(ValueError, diagnostic):
                    run_e2e._validate_telemetry(payload)

    def test_partial_telemetry_does_not_claim_completed_session_execution(self):
        payload = self._telemetry_payload()
        payload["status"] = "partial"
        payload["counts"].update({"sessions": 1, "primary_executions": 0})
        run_e2e._validate_telemetry(payload)

    def test_failed_test_keeps_original_failure_when_telemetry_missing(self):
        with self._scripts({"test_fail.py": "import sys\nprint('original failure', file=sys.stderr)\nsys.exit(3)\n"}, telemetry=False) as root:
            result = run_e2e.run_suite([root / "test_fail.py"], log_dir=root / "logs")[0]
            self.assertTrue(result.detail.startswith("original failure"))
            self.assertIn("missing telemetry fixture", result.detail)
            self.assertTrue(result.runner_error)

    def test_failed_test_retains_valid_partial_telemetry(self):
        script = "import json,os,sys\np=os.environ['ORCHESTRATOR_E2E_TELEMETRY_PATH']\nd=json.load(open(p))\nd['status']='partial'\njson.dump(d,open(p,'w'))\nsys.exit(3)\n"
        with self._scripts({"test_fail.py": script}) as root:
            result = run_e2e.run_suite([root / "test_fail.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertFalse(result.runner_error)
            self.assertIsNotNone(result.telemetry)
            assert result.telemetry is not None
            self.assertEqual(result.telemetry["status"], "partial")

    def test_failed_test_returns_nonzero(self):
        with self._scripts({"test_fail.py": "import sys\nsys.exit(3)\n"}) as root:
            results = run_e2e.run_suite([root / "test_fail.py"], log_dir=root / "logs")
            self.assertEqual(results[0].status, "failed")
            self.assertEqual(results[0].returncode, 3)

    def test_spawn_failure_is_controlled_failed_result(self):
        with self._scripts({"test_spawn.py": "print('unused')\n"}) as root, patch("run_e2e.subprocess.Popen", side_effect=OSError("spawn denied")):
            result = run_e2e.run_suite([root / "test_spawn.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertIn("process spawn failure: OSError: spawn denied", result.detail)
            self.assertTrue(result.runner_error)

    def test_inaccessible_log_directory_is_stable_runner_error(self):
        with self._scripts({"test_pass.py": "print('unused')\n"}) as root:
            log_path = root / "not-a-directory"
            log_path.write_text("occupied", encoding="utf-8")
            stderr = StringIO()
            with patch("run_e2e.discover_tests", return_value=[root / "test_pass.py"]), redirect_stdout(StringIO()), redirect_stderr(stderr):
                exit_code = run_e2e.main(["--log-dir", str(log_path)])
            self.assertEqual(exit_code, run_e2e.EXIT_RUNNER_ERROR)
            self.assertIn("cannot prepare log directory", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_fail_fast_does_not_run_later_test(self):
        with self._scripts({"test_fail.py": "raise RuntimeError('stop')\n", "test_later.py": "from pathlib import Path\nPath(__file__).with_suffix('.ran').touch()\n"}) as root:
            results = run_e2e.run_suite([root / "test_fail.py", root / "test_later.py"], log_dir=root / "logs")
            self.assertEqual([result.status for result in results], ["failed", "not-run"])
            self.assertFalse((root / "test_later.ran").exists())

    def test_continue_after_failure_runs_later_test(self):
        with self._scripts({"test_fail.py": "raise RuntimeError('stop')\n", "test_later.py": "from pathlib import Path\nPath(__file__).with_suffix('.ran').touch()\n"}) as root:
            results = run_e2e.run_suite([root / "test_fail.py", root / "test_later.py"], fail_fast=False, log_dir=root / "logs")
            self.assertEqual([result.status for result in results], ["failed", "passed"])
            self.assertTrue((root / "test_later.ran").exists())

    def test_unknown_filter_is_error_not_success(self):
        with self.assertRaisesRegex(ValueError, "matched no tests"):
            run_e2e.select_tests([Path("test_known.py")], "missing")

    def test_timeout_is_failure(self):
        with self._scripts({"test_slow.py": "import time\ntime.sleep(2)\n"}) as root:
            result = run_e2e.run_suite([root / "test_slow.py"], timeout=0.01, log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertIn("timeout", result.detail)

    def test_timeout_terminates_descendant_process_group(self):
        child = "import signal,time,sys; signal.signal(signal.SIGTERM, lambda *_: (open(sys.argv[1], 'w').write('terminated'), sys.exit(0))); time.sleep(10)"
        script = f"import subprocess,sys,time\nsubprocess.Popen([sys.executable, '-c', {child!r}, str(__file__) + '.terminated'])\ntime.sleep(10)\n"
        with self._scripts({"test_child.py": script}) as root:
            result = run_e2e.run_suite([root / "test_child.py"], timeout=0.2, log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertEqual((root / "test_child.py.terminated").read_text(), "terminated")

    def test_no_timeout_does_not_wait_for_descendant_pipe_eof(self):
        child = "import signal,time,sys; signal.signal(signal.SIGTERM, lambda *_: (open(sys.argv[1], 'w').write('terminated'), sys.exit(0))); open(sys.argv[2], 'w').write('ready'); time.sleep(10)"
        script = f"import pathlib,subprocess,sys,time\nready=str(__file__) + '.ready'\nsubprocess.Popen([sys.executable, '-c', {child!r}, str(__file__) + '.terminated', ready])\nwhile not pathlib.Path(ready).exists(): time.sleep(0.01)\n"
        with self._scripts({"test_child.py": script}) as root:
            result = run_e2e.run_suite([root / "test_child.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "passed")
            self.assertLess(result.duration, 3)
            self.assertEqual((root / "test_child.py.terminated").read_text(), "terminated")

    def test_process_crash_is_failure(self):
        with self._scripts({"test_crash.py": "import os\nos._exit(7)\n"}) as root:
            result = run_e2e.run_suite([root / "test_crash.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.returncode, 7)

    def test_stdout_and_stderr_are_preserved(self):
        with self._scripts({"test_output.py": "import sys\nprint('saved stdout')\nprint('saved stderr', file=sys.stderr)\n"}) as root:
            result = run_e2e.run_suite([root / "test_output.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "passed")
            self.assertEqual(result.stdout, "saved stdout\n")
            self.assertEqual(result.stderr, "saved stderr\n")

    def test_output_read_failure_cannot_pass(self):
        with self._scripts({"test_pass.py": "print('output')\n"}) as root, patch.object(Path, "read_text", side_effect=OSError("read denied")):
            result = run_e2e.run_suite([root / "test_pass.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertIn("read failure: OSError: read denied", result.detail)

    def test_missing_output_file_cannot_pass(self):
        with self._scripts({"test_pass.py": "print('output')\n"}) as root, patch.object(Path, "read_text", side_effect=FileNotFoundError("missing output")):
            result = run_e2e.run_suite([root / "test_pass.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertIn("read failure: FileNotFoundError: missing output", result.detail)

    def test_failure_log_write_failure_cannot_pass(self):
        with self._scripts({"test_pass.py": "print('output')\n"}) as root, patch.object(Path, "write_text", side_effect=OSError("write denied")):
            result = run_e2e.run_suite([root / "test_pass.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertIn("failure log write failure: OSError: write denied", result.detail)
            self.assertIsNone(result.log_path)

    def test_cleanup_failure_augments_child_failure(self):
        with self._scripts({"test_fail.py": "import sys\nprint('decisive child failure', file=sys.stderr)\nsys.exit(4)\n"}) as root, patch("run_e2e._terminate_process_group", side_effect=OSError("cleanup denied")):
            result = run_e2e.run_suite([root / "test_fail.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.returncode, 4)
            self.assertTrue(result.detail.startswith("decisive child failure"))
            self.assertIn("process-group cleanup failure: OSError: cleanup denied", result.detail)

    def test_stderr_is_preserved_in_log_and_detail(self):
        with self._scripts({"test_fail.py": "import sys\nprint('decisive stderr', file=sys.stderr)\nsys.exit(1)\n"}) as root:
            result = run_e2e.run_suite([root / "test_fail.py"], log_dir=root / "logs")[0]
            self.assertIn("decisive stderr", result.stderr)
            self.assertIn("decisive stderr", result.detail)
            self.assertIsNotNone(result.log_path)
            assert result.log_path is not None
            log = result.log_path.read_text(encoding="utf-8")
            self.assertIn("decisive stderr", log)
            self.assertIn("DETAIL", log)

    def test_report_shows_created_failure_log_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "failed.log"
            log_path.write_text("failure", encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                run_e2e.report([run_e2e.TestResult("test_fail.py", "failed", log_path=log_path)], 0.1)
            self.assertIn(str(log_path), output.getvalue())

    def test_failed_log_write_does_not_report_stale_log(self):
        with self._scripts({"test_fail.py": "raise RuntimeError('failure')\n"}) as root:
            logs = root / "logs"
            logs.mkdir()
            stale = logs / "test_fail.log"
            stale.write_text("stale", encoding="utf-8")
            original_write_text = Path.write_text
            def write_text(path, *args, **kwargs):
                if path == stale:
                    raise OSError("write denied")
                return original_write_text(path, *args, **kwargs)
            with patch.object(Path, "write_text", write_text):
                result = run_e2e.run_suite([root / "test_fail.py"], log_dir=logs)[0]
            self.assertIsNone(result.log_path)
            self.assertFalse(stale.exists())

    def test_each_test_runs_once_without_retry(self):
        with self._scripts({"test_once.py": "from pathlib import Path\np=Path(__file__).with_suffix('.count')\np.write_text(str(int(p.read_text()) + 1) if p.exists() else '1')\nraise RuntimeError('fail')\n"}) as root:
            run_e2e.run_suite([root / "test_once.py"], fail_fast=False, log_dir=root / "logs")
            self.assertEqual((root / "test_once.count").read_text(), "1")

    def test_each_subprocess_receives_unique_telemetry_path(self):
        script = "from pathlib import Path\nimport os\nPath(__file__).with_suffix('.path').write_text(os.environ['ORCHESTRATOR_E2E_TELEMETRY_PATH'])\n"
        with self._scripts({"test_one.py": script, "test_two.py": script}) as root:
            results = run_e2e.run_suite([root / "test_one.py", root / "test_two.py"], fail_fast=False, log_dir=root / "logs")
            self.assertEqual([result.status for result in results], ["passed", "passed"])
            self.assertNotEqual((root / "test_one.path").read_text(), (root / "test_two.path").read_text())

    def test_parent_pythonoptimize_cannot_disable_live_assertions(self):
        with self._scripts({"test_assert.py": "assert False, 'must execute'\n"}) as root, patch.dict("run_e2e.os.environ", {"PYTHONOPTIMIZE": "1"}):
            result = run_e2e.run_suite([root / "test_assert.py"], log_dir=root / "logs")[0]
            self.assertEqual(result.status, "failed")
            self.assertIn("AssertionError: must execute", result.stderr)

    def test_not_run_is_not_counted_as_passed(self):
        results = [run_e2e.TestResult("failed.py", "failed"), run_e2e.TestResult("later.py", "not-run")]
        output = StringIO()
        with redirect_stdout(output):
            run_e2e.report(results, 1.0)
        self.assertIn("passed=0", output.getvalue())
        self.assertIn("not-run=1", output.getvalue())

    def test_duplicate_discovery_is_rejected(self):
        with self._scripts({"test_live.py": "print('live')\n"}) as root:
            path = root / "test_live.py"
            with self.assertRaisesRegex(ValueError, "duplicate"):
                run_e2e.discover_tests(root, [path, path], ("test_live.py",))

    def test_empty_discovery_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                run_e2e.discover_tests(Path(temporary), expected_names=("test_expected.py",))

    def test_unexpected_and_out_of_root_discovery_are_rejected(self):
        with self._scripts({"test_unexpected.py": "print('unexpected')\n"}) as root:
            with self.assertRaisesRegex(ValueError, "unexpected"):
                run_e2e.discover_tests(root, expected_names=("test_expected.py",))
            with tempfile.TemporaryDirectory() as outside:
                path = Path(outside) / "test_expected.py"
                path.write_text("print('outside')\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    run_e2e.discover_tests(root, [path], ("test_expected.py",))

    def test_symlink_discovery_is_rejected(self):
        with self._scripts({"test_real.py": "print('real')\n"}) as root:
            link = root / "test_expected.py"
            link.symlink_to(root / "test_real.py")
            with self.assertRaisesRegex(ValueError, "symlink"):
                run_e2e.discover_tests(root, [link], ("test_expected.py",))

    def test_main_exit_codes_and_filter(self):
        tests = [Path("test_pass.py"), Path("test_fail.py")]
        with patch("run_e2e.discover_tests", return_value=tests), patch("run_e2e.run_suite", return_value=[run_e2e.TestResult("test_fail.py", "failed")]) as run, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(run_e2e.main(["--filter", "fail"]), run_e2e.EXIT_TEST_FAILURE)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], [Path("test_fail.py")])
        with patch("run_e2e.discover_tests", return_value=tests), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(run_e2e.main(["--filter", "unknown"]), run_e2e.EXIT_RUNNER_ERROR)

    def test_suite_level_failure_is_controlled_without_traceback(self):
        stderr = StringIO()
        with patch("run_e2e.discover_tests", side_effect=RuntimeError("inventory unavailable")), redirect_stdout(StringIO()), redirect_stderr(stderr):
            exit_code = run_e2e.main([])
        self.assertEqual(exit_code, run_e2e.EXIT_RUNNER_ERROR)
        self.assertIn("RuntimeError: inventory unavailable", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_keyboard_interrupt_is_not_pass(self):
        with self._scripts({"test_interrupt.py": "print('unused')\n"}) as root, patch("run_e2e.subprocess.Popen", side_effect=KeyboardInterrupt):
            results = run_e2e.run_suite([root / "test_interrupt.py"], log_dir=root / "logs")
        self.assertEqual(results[0].status, "interrupted")
        with patch("run_e2e.discover_tests", return_value=[Path("test_interrupt.py")]), patch("run_e2e.run_suite", return_value=results), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(run_e2e.main([]), run_e2e.EXIT_INTERRUPTED)

    def test_termination_signal_becomes_cleanup_interrupt(self):
        with self.assertRaises(KeyboardInterrupt):
            with run_e2e._termination_as_interrupt():
                os.kill(os.getpid(), signal.SIGTERM)

    def test_exit_codes_are_distinct_and_documented(self):
        self.assertEqual((run_e2e.EXIT_SUCCESS, run_e2e.EXIT_TEST_FAILURE, run_e2e.EXIT_RUNNER_ERROR, run_e2e.EXIT_INTERRUPTED), (0, 1, 2, 130))
        output = StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(output):
            run_e2e.main(["--help"])
        self.assertIn("Exit codes: 0=success, 1=test failure, 2=runner error, 130=interrupted", output.getvalue())

    def test_main_prints_aggregate_report_when_results_exist(self):
        output = StringIO()
        results = [run_e2e.TestResult("test_fail.py", "failed")]
        with patch("run_e2e.discover_tests", return_value=[Path("test_fail.py")]), patch("run_e2e.run_suite", return_value=results), redirect_stdout(output), redirect_stderr(StringIO()):
            run_e2e.main([])
        self.assertIn("TOTAL", output.getvalue())

    def test_main_returns_runner_error_for_result_infrastructure_failure(self):
        results = [run_e2e.TestResult("test_spawn.py", "failed", runner_error=True)]
        with patch("run_e2e.discover_tests", return_value=[Path("test_spawn.py")]), patch("run_e2e.run_suite", return_value=results), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(run_e2e.main([]), run_e2e.EXIT_RUNNER_ERROR)

    def test_json_report_path_inside_repository_is_rejected(self):
        stderr = StringIO()
        report = run_e2e.ROOT / "generated-report.json"
        with redirect_stdout(StringIO()), redirect_stderr(stderr):
            self.assertEqual(run_e2e.main(["--json-report", str(report)]), run_e2e.EXIT_RUNNER_ERROR)
        self.assertIn("must be outside repository", stderr.getvalue())
        self.assertFalse(report.exists())

    def test_duration_report_contains_per_test_and_aggregate(self):
        output = StringIO()
        with redirect_stdout(output):
            run_e2e.report([run_e2e.TestResult("test_pass.py", "passed", duration=1.25)], 2.5)
        self.assertIn("1.25s", output.getvalue())
        self.assertIn("TOTAL 2.50s", output.getvalue())

    def test_duration_statistics_are_deterministic(self):
        cases = (
            ([], {"count": 0, "unavailable": 2, "sum": 0.0, "median": None, "p95": None}),
            ([5.0], {"count": 1, "unavailable": 0, "sum": 5.0, "median": 5.0, "p95": 5.0}),
            ([1.0, 3.0], {"count": 2, "unavailable": 0, "sum": 4.0, "median": 2.0, "p95": 3.0}),
            ([3.0, 1.0, 2.0], {"count": 3, "unavailable": 0, "sum": 6.0, "median": 2.0, "p95": 3.0}),
            ([1.0, 2.0, 3.0, 4.0], {"count": 4, "unavailable": 0, "sum": 10.0, "median": 2.5, "p95": 4.0}),
        )
        for values, expected in cases:
            with self.subTest(values=values):
                unavailable = 2 if not values else 0
                self.assertEqual(run_e2e._duration_summary(values, unavailable), expected)

    def test_nearest_rank_p95_uses_ceiling_rank(self):
        self.assertEqual(run_e2e._duration_summary([float(value) for value in range(1, 21)])["p95"], 19.0)
        self.assertEqual(run_e2e._duration_summary([1.0, 2.0])["p95"], 2.0)

    def test_aggregate_combines_multiple_fixtures_and_unavailable(self):
        first = self._telemetry_payload()
        second = self._telemetry_payload()
        first["durations_seconds"]["subagent"] = {"values": [1.0], "unavailable": 0}
        first["counts"].update({"task_attempts": 1, "task_successes": 1})
        first["ordered_agents"] = ["orchestrator-discovery"]
        second["durations_seconds"]["subagent"] = {"values": [], "unavailable": 1}
        second["counts"].update({"task_attempts": 1, "task_incomplete": 1})
        aggregate = run_e2e.aggregate_telemetry([run_e2e.TestResult("one", "passed", telemetry=first), run_e2e.TestResult("two", "failed", telemetry=second), run_e2e.TestResult("three", "not-run")], 4.0)
        self.assertEqual(aggregate["counts"]["task_attempts"], 2)
        self.assertEqual(aggregate["durations_seconds"]["subagent"]["unavailable"], 1)
        self.assertEqual(aggregate["tests"]["telemetry_unavailable"], 1)
        self.assertEqual(aggregate["ordered_agents"], ["orchestrator-discovery"])

    def test_json_report_cli_writes_schema_atomically(self):
        telemetry = self._telemetry_payload()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reports" / "e2e.json"
            results = [run_e2e.TestResult("test_pass.py", "passed", telemetry=telemetry)]
            with patch("run_e2e.discover_tests", return_value=[Path("test_pass.py")]), patch("run_e2e.run_suite", return_value=results), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                exit_code = run_e2e.main(["--json-report", str(path)])
            self.assertEqual(exit_code, run_e2e.EXIT_SUCCESS)
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["tests"]["statuses"]["passed"], 1)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_json_report_write_failure_is_runner_error(self):
        telemetry = self._telemetry_payload()
        results = [run_e2e.TestResult("test_pass.py", "passed", telemetry=telemetry)]
        with tempfile.TemporaryDirectory() as temporary, patch("run_e2e.discover_tests", return_value=[Path("test_pass.py")]), patch("run_e2e.run_suite", return_value=results), patch("run_e2e._atomic_write_json", side_effect=OSError("write denied")) as write, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(run_e2e.main(["--json-report", str(Path(temporary) / "report.json")]), run_e2e.EXIT_RUNNER_ERROR)
            write.assert_called_once()

    @staticmethod
    def _scripts(files, telemetry=True):
        class Scripts:
            def __enter__(self):
                self.temporary = tempfile.TemporaryDirectory()
                root = Path(self.temporary.name)
                for name, content in files.items():
                    prefix = ""
                    if telemetry:
                        prefix = f"import json as _json, os as _os\nwith open(_os.environ['{run_e2e.TELEMETRY_PATH_ENV}'], 'w', encoding='utf-8') as _telemetry: _json.dump({RunnerTests._telemetry_payload()!r}, _telemetry)\n"
                    (root / name).write_text(prefix + content, encoding="utf-8")
                return root

            def __exit__(self, *_args):
                self.temporary.cleanup()
        return Scripts()

    @staticmethod
    def _telemetry_payload():
        payload = {
            "schema_version": 1,
            "status": "complete",
            "durations_seconds": {name: {"values": [], "unavailable": 0} for name in run_e2e.DURATION_METRICS},
            "counts": {name: 0 for name in run_e2e.COUNT_METRICS},
            "ordered_agents": [],
        }
        payload["counts"]["serve_startups"] = 1
        payload["counts"]["sessions"] = 1
        payload["counts"]["primary_executions"] = 1
        payload["durations_seconds"]["prompt_to_idle"]["values"] = [0.1]
        payload["durations_seconds"]["polling"]["values"] = [0.1]
        for name in ("fixture_setup", "environment_setup", "process_startup_to_health", "agent_inventory_loading", "cleanup", "total"):
            payload["durations_seconds"][name]["values"] = [0.1]
        return payload


if __name__ == "__main__":
    unittest.main()
