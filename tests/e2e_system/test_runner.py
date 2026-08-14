#!/usr/bin/env python3

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_e2e


class RunnerTests(unittest.TestCase):
    def test_failed_test_returns_nonzero(self):
        with self._scripts({"test_fail.py": "import sys\nsys.exit(3)\n"}) as root:
            results = run_e2e.run_suite([root / "test_fail.py"], log_dir=root / "logs")
            self.assertEqual(results[0].status, "failed")
            self.assertEqual(results[0].returncode, 3)

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

    def test_stderr_is_preserved_in_log_and_detail(self):
        with self._scripts({"test_fail.py": "import sys\nprint('decisive stderr', file=sys.stderr)\nsys.exit(1)\n"}) as root:
            result = run_e2e.run_suite([root / "test_fail.py"], log_dir=root / "logs")[0]
            self.assertIn("decisive stderr", result.stderr)
            self.assertIn("decisive stderr", result.detail)
            self.assertIsNotNone(result.log_path)
            assert result.log_path is not None
            self.assertIn("decisive stderr", result.log_path.read_text(encoding="utf-8"))

    def test_each_test_runs_once_without_retry(self):
        with self._scripts({"test_once.py": "from pathlib import Path\np=Path(__file__).with_suffix('.count')\np.write_text(str(int(p.read_text()) + 1) if p.exists() else '1')\nraise RuntimeError('fail')\n"}) as root:
            run_e2e.run_suite([root / "test_once.py"], fail_fast=False, log_dir=root / "logs")
            self.assertEqual((root / "test_once.count").read_text(), "1")

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
            self.assertEqual(run_e2e.main(["--filter", "fail"]), 1)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], [Path("test_fail.py")])
        with patch("run_e2e.discover_tests", return_value=tests), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(run_e2e.main(["--filter", "unknown"]), 2)

    def test_duration_report_contains_per_test_and_aggregate(self):
        output = StringIO()
        with redirect_stdout(output):
            run_e2e.report([run_e2e.TestResult("test_pass.py", "passed", duration=1.25)], 2.5)
        self.assertIn("1.25s", output.getvalue())
        self.assertIn("TOTAL 2.50s", output.getvalue())

    @staticmethod
    def _scripts(files):
        class Scripts:
            def __enter__(self):
                self.temporary = tempfile.TemporaryDirectory()
                root = Path(self.temporary.name)
                for name, content in files.items():
                    (root / name).write_text(content, encoding="utf-8")
                return root

            def __exit__(self, *_args):
                self.temporary.cleanup()
        return Scripts()


if __name__ == "__main__":
    unittest.main()
