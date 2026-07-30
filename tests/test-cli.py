import subprocess
import sys
import tempfile
import unittest
import os
import importlib.util
import base64
from unittest.mock import MagicMock, patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "opencode-agents.py"
SPEC = importlib.util.spec_from_file_location("opencode_agents", CLI)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load opencode-agents.py")
OPENCODE_AGENTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPENCODE_AGENTS)


class CliTests(unittest.TestCase):
    def test_install_update_and_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "target"
            backup = root / "backup"
            (source / "agents").mkdir(parents=True)
            (source / "protocols").mkdir(parents=True)
            (source / "agents/example.md").write_text("'__OPENCODE_PROTOCOL_PATH_YAML__': allow\nRead __OPENCODE_PROTOCOL_PATH_TEXT__\n", encoding="utf-8")
            (source / "protocols/example.md").write_text("protocol-v1\n", encoding="utf-8")

            self.run_cli(source, target, "install")
            self.assertEqual((target / "agents/example.md").read_text(), f"'{target}/protocols/orchestrator-v2.md': allow\nRead {target}/protocols/orchestrator-v2.md\n")
            self.assertIn("caveman", (target / "AGENTS.md").read_text())
            self.run_cli(source, target, "install")

            (target / "agents/example.md").write_text("local-change\n", encoding="utf-8")
            (source / "agents/example.md").write_text("agent-v2 __OPENCODE_PROTOCOL_PATH_TEXT__\n", encoding="utf-8")
            self.run_cli(source, target, "update", "--backup-dir", str(backup))
            self.assertEqual((target / "agents/example.md").read_text(), f"agent-v2 {target}/protocols/orchestrator-v2.md\n")
            self.assertEqual((backup / "agents/example.md").read_text(), "local-change\n")
            result = self.run_cli(source, target, "status", capture_output=True)
            self.assertIn("current agents/example.md", result.stdout)

            legacy = target / "agents/orchestrator-00-main-caveman.md"
            built_in = target / "agents/build.md"
            unknown = target / "agents/user-agent.md"
            legacy.write_text("legacy\n", encoding="utf-8")
            built_in.write_text("built-in\n", encoding="utf-8")
            unknown.write_text("user\n", encoding="utf-8")
            self.run_cli(source, target, "update", "--backup-dir", str(backup), "--prune-legacy")
            self.assertFalse(legacy.exists())
            self.assertEqual(built_in.read_text(), "built-in\n")
            self.assertEqual(unknown.read_text(), "user\n")

    def test_opencode_config_dir_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "config"
            (source / "agents").mkdir(parents=True)
            (source / "protocols").mkdir(parents=True)
            (source / "agents/example.md").write_text("agent\n", encoding="utf-8")
            (source / "protocols/example.md").write_text("protocol\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["OPENCODE_CONFIG_DIR"] = str(target)
            subprocess.run([sys.executable, str(CLI), "--source", str(source), "install"], check=True, env=environment)
            self.assertEqual((target / "agents/example.md").read_text(), "agent\n")

    def test_repository_prompts_render_target_protocol_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(ROOT, target, "install")
            prompts = sorted((target / "agents").glob("*.md"))
            self.assertEqual(len(prompts), 9)
            for prompt in prompts:
                content = prompt.read_text(encoding="utf-8")
                self.assertNotIn("__OPENCODE_PROTOCOL_PATH_", content)
                self.assertIn(str(target / "protocols/orchestrator-v2.md"), content)
            self.assertEqual([prompt.name for prompt in prompts], ["orchestrator-00-main.md", "orchestrator-10-workflow-bootstrap.md", "orchestrator-20-planner.md", "orchestrator-30-planner-senior.md", "orchestrator-40-executor.md", "orchestrator-50-validator.md", "orchestrator-60-mini-reviewer.md", "orchestrator-70-review-aggregator.md", "orchestrator-80-final-reviewer.md"])
            self.assertIn("name: orchestrator", (target / "agents/orchestrator-00-main.md").read_text(encoding="utf-8"))
            self.assertNotIn("Load `caveman`", (target / "agents/orchestrator-00-main.md").read_text(encoding="utf-8"))
            self.assertIn("caveman` skill is available", (target / "agents/orchestrator-40-executor.md").read_text(encoding="utf-8"))

    def test_path_writer_for_windows_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            target = root / "target" / "agent.md"
            source.write_text("source\n", encoding="utf-8")
            OPENCODE_AGENTS.atomic_write_path(source, b"rendered\n", target)
            self.assertEqual(target.read_text(), "rendered\n")

    def test_github_api_source_does_not_need_clone(self):
        tree = {"tree": [{"path": "AGENTS.md", "type": "blob", "sha": "a"}, {"path": "agents/example.md", "type": "blob", "sha": "b"}, {"path": "protocols/example.md", "type": "blob", "sha": "c"}]}
        blobs = {"a": "global\n", "b": "agent\n", "c": "protocol\n"}

        def github_response(url, token):
            if "/git/trees/" in url:
                return tree
            sha = url.rsplit("/", 1)[1]
            return {"content": base64.b64encode(blobs[sha].encode()).decode()}

        with patch.object(OPENCODE_AGENTS, "github_json", side_effect=github_response):
            with OPENCODE_AGENTS.prepared_source(None, "kostazol/opencode-agents", "main", "https://api.github.test") as source:
                self.assertEqual((source / "agents/example.md").read_text(), "agent\n")
                self.assertEqual((source / "protocols/example.md").read_text(), "protocol\n")

    def test_repository_name_accepts_url_and_owner_name(self):
        self.assertEqual(OPENCODE_AGENTS.repository_name("kostazol/opencode-agents"), "kostazol/opencode-agents")
        self.assertEqual(OPENCODE_AGENTS.repository_name("https://github.com/kostazol/opencode-agents.git"), "kostazol/opencode-agents")
        with self.assertRaisesRegex(RuntimeError, "unsupported repository URL"):
            OPENCODE_AGENTS.repository_name("http://github.com/kostazol/opencode-agents")
        with self.assertRaisesRegex(RuntimeError, "unsupported repository URL"):
            OPENCODE_AGENTS.repository_name("https://github.com:443/kostazol/opencode-agents")

    def test_github_json_reports_invalid_json(self):
        response = MagicMock()
        response.read.return_value = b"{"
        context = MagicMock()
        context.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = context
        with patch.object(OPENCODE_AGENTS, "build_opener", return_value=opener):
            with self.assertRaisesRegex(RuntimeError, "GitHub API returned invalid JSON"):
                OPENCODE_AGENTS.github_json("https://api.github.com/repos/kostazol/opencode-agents", None)

    @staticmethod
    def run_cli(source, target, command, *arguments, capture_output=False):
        return subprocess.run([sys.executable, str(CLI), "--source", str(source), "--target", str(target), command, *arguments], check=True, text=True, capture_output=capture_output)


if __name__ == "__main__":
    unittest.main()
