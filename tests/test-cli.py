import subprocess
import sys
import tempfile
import unittest
import os
import importlib.util
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
            self.run_cli(source, target, "install")

            (target / "agents/example.md").write_text("local-change\n", encoding="utf-8")
            (source / "agents/example.md").write_text("agent-v2 __OPENCODE_PROTOCOL_PATH_TEXT__\n", encoding="utf-8")
            self.run_cli(source, target, "update", "--backup-dir", str(backup))
            self.assertEqual((target / "agents/example.md").read_text(), f"agent-v2 {target}/protocols/orchestrator-v2.md\n")
            self.assertEqual((backup / "agents/example.md").read_text(), "local-change\n")
            result = self.run_cli(source, target, "status", capture_output=True)
            self.assertIn("current agents/example.md", result.stdout)

            legacy = target / "agents/build.md"
            unknown = target / "agents/user-agent.md"
            legacy.write_text("legacy\n", encoding="utf-8")
            unknown.write_text("user\n", encoding="utf-8")
            self.run_cli(source, target, "update", "--backup-dir", str(backup), "--prune-legacy")
            self.assertFalse(legacy.exists())
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
            prompts = list((target / "agents").glob("*.md"))
            self.assertEqual(len(prompts), 9)
            for prompt in prompts:
                content = prompt.read_text(encoding="utf-8")
                self.assertNotIn("__OPENCODE_PROTOCOL_PATH_", content)
                self.assertIn(str(target / "protocols/orchestrator-v2.md"), content)

    def test_path_writer_for_windows_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            target = root / "target" / "agent.md"
            source.write_text("source\n", encoding="utf-8")
            OPENCODE_AGENTS.atomic_write_path(source, b"rendered\n", target)
            self.assertEqual(target.read_text(), "rendered\n")

    @staticmethod
    def run_cli(source, target, command, *arguments, capture_output=False):
        return subprocess.run([sys.executable, str(CLI), "--source", str(source), "--target", str(target), command, *arguments], check=True, text=True, capture_output=capture_output)


if __name__ == "__main__":
    unittest.main()
