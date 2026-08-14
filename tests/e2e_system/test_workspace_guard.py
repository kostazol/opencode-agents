#!/usr/bin/env python3

from dataclasses import replace
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import unittest

from harness import assert_workspace_unchanged, capture_workspace_snapshot


class WorkspaceGuardTests(unittest.TestCase):
    def test_detects_source_file_change(self):
        self._assert_mutation_detected(lambda root: (root / "src/example.py").write_text("changed\n", encoding="utf-8"), "src/example.py")

    def test_detects_test_file_deletion(self):
        self._assert_mutation_detected(lambda root: (root / "tests/test_example.py").unlink(), "tests/test_example.py")

    def test_detects_product_file_rename(self):
        self._assert_mutation_detected(lambda root: (root / "src/example.py").rename(root / "src/renamed.py"), "src/example.py")

    def test_detects_new_root_file(self):
        self._assert_mutation_detected(lambda root: (root / "unexpected.txt").write_text("new\n", encoding="utf-8"), "unexpected.txt")

    def test_detects_repository_instruction_change(self):
        self._assert_mutation_detected(lambda root: (root / "AGENTS.md").write_text("changed\n", encoding="utf-8"), "AGENTS.md")

    def test_detects_agent_fixture_change(self):
        self._assert_mutation_detected(lambda root: (root / ".opencode/agents/orchestrator-analyst.md").write_text("changed\n", encoding="utf-8"), ".opencode/agents/orchestrator-analyst.md")

    def test_ignores_opencode_runtime_dependencies(self):
        with self._workspace() as root:
            before = capture_workspace_snapshot(root, Path("1_orchestrator/e2e"))
            runtime = root / ".opencode/node_modules/runtime"
            runtime.mkdir(parents=True)
            (runtime / "package.js").write_text("generated\n", encoding="utf-8")
            (root / ".opencode/package.json").write_text("{}\n", encoding="utf-8")
            (root / ".opencode/package-lock.json").write_text("{}\n", encoding="utf-8")
            assert_workspace_unchanged(before, capture_workspace_snapshot(root, Path("1_orchestrator/e2e")))

    def test_detects_neighbor_workflow_change(self):
        self._assert_mutation_detected(lambda root: (root / "1_orchestrator/neighbor/plan.md").write_text("changed\n", encoding="utf-8"), "1_orchestrator/neighbor/plan.md")

    def test_detects_artifact_under_wrong_request(self):
        self._assert_mutation_detected(self._write_wrong_request, "1_orchestrator/wrong/discovery.md")

    def test_detects_git_status_change(self):
        with self._workspace() as root:
            before = capture_workspace_snapshot(root, Path("1_orchestrator/e2e"))
            after = replace(capture_workspace_snapshot(root, Path("1_orchestrator/e2e")), git_status=" M src/example.py\n")
            with self.assertRaisesRegex(AssertionError, "git status changed"):
                assert_workspace_unchanged(before, after)

    def test_allows_only_exact_request_target_and_preserves_initial_changes(self):
        with self._workspace() as root:
            (root / "src/example.py").write_text("user change before run\n", encoding="utf-8")
            before = capture_workspace_snapshot(root, Path("1_orchestrator/e2e"))
            (root / "1_orchestrator/e2e/stages").mkdir(parents=True)
            (root / "1_orchestrator/e2e/stages/01.md").write_text("allowed\n", encoding="utf-8")
            assert_workspace_unchanged(before, capture_workspace_snapshot(root, Path("1_orchestrator/e2e")))

    def test_detects_symlink_target_change(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unavailable")
        self._assert_mutation_detected(self._change_symlink, "source-link")

    def _assert_mutation_detected(self, mutate, expected_path):
        with self._workspace() as root:
            before = capture_workspace_snapshot(root, Path("1_orchestrator/e2e"))
            mutate(root)
            after = capture_workspace_snapshot(root, Path("1_orchestrator/e2e"))
            with self.assertRaisesRegex(AssertionError, expected_path):
                assert_workspace_unchanged(before, after)

    @staticmethod
    def _change_symlink(root):
        link = root / "source-link"
        link.unlink()
        link.symlink_to("tests/test_example.py")

    @staticmethod
    def _write_wrong_request(root):
        target = root / "1_orchestrator/wrong"
        target.mkdir()
        (target / "discovery.md").write_text("new\n", encoding="utf-8")

    @staticmethod
    @contextmanager
    def _workspace():
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / ".opencode/agents").mkdir(parents=True)
            (root / "1_orchestrator/neighbor").mkdir(parents=True)
            (root / "src/example.py").write_text("original\n", encoding="utf-8")
            (root / "tests/test_example.py").write_text("original\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("instructions\n", encoding="utf-8")
            (root / ".opencode/agents/orchestrator-analyst.md").write_text("agent\n", encoding="utf-8")
            (root / "1_orchestrator/neighbor/plan.md").write_text("neighbor\n", encoding="utf-8")
            if hasattr(os, "symlink"):
                (root / "source-link").symlink_to("src/example.py")
            yield root


if __name__ == "__main__":
    unittest.main()
