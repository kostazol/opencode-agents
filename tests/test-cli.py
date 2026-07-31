import subprocess
import sys
import tempfile
import unittest
import os
import importlib.util
import base64
import re
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
            self.assertEqual(len(prompts), 11)
            for prompt in prompts:
                content = prompt.read_text(encoding="utf-8")
                self.assertNotIn("__OPENCODE_PROTOCOL_PATH_", content)
                self.assertIn(str(target / "protocols/orchestrator-v2.md"), content)
            self.assertEqual([prompt.name for prompt in prompts], ["orchestrator-00-main.md", "orchestrator-01-single-model-main.md", "orchestrator-10-workflow-bootstrap.md", "orchestrator-20-planner.md", "orchestrator-25-planner-full.md", "orchestrator-30-planner-senior.md", "orchestrator-40-executor.md", "orchestrator-50-validator.md", "orchestrator-60-mini-reviewer.md", "orchestrator-70-review-aggregator.md", "orchestrator-80-final-reviewer.md"])
            self.assertIn("name: orchestrator", (target / "agents/orchestrator-00-main.md").read_text(encoding="utf-8"))
            single_model = (target / "agents/orchestrator-01-single-model-main.md").read_text(encoding="utf-8")
            self.assertIn("name: orchestrator-single-model", single_model)
            self.assertIn("WORKFLOW_PROFILE: SINGLE_MODEL", single_model)
            self.assertNotIn("orchestrator-30-planner-senior", single_model)
            self.assertNotIn("orchestrator-80-final-reviewer", single_model)
            self.assertNotIn("\nmodel:", single_model)
            self.assertNotIn("\nmodel:", (target / "agents/orchestrator-25-planner-full.md").read_text(encoding="utf-8"))
            self.assertNotIn("Load `caveman`", (target / "agents/orchestrator-00-main.md").read_text(encoding="utf-8"))
            self.assertIn("caveman` skill is available", (target / "agents/orchestrator-40-executor.md").read_text(encoding="utf-8"))

    def test_workflow_artifact_permissions_allow_root_relative_paths(self):
        def permission_rules(content, permission):
            lines = content.splitlines()
            start = lines.index(f"  {permission}:") + 1
            rules = []
            for line in lines[start:]:
                if not line.startswith("    "):
                    break
                match = re.fullmatch(r'    (["\'])(.*)\1: (allow|ask|deny)', line)
                if match:
                    rules.append((match.group(2), match.group(3)))
            return rules

        def evaluate(rules, path):
            result = "ask"
            path = path.replace("\\", "/")
            for pattern, action in rules:
                pattern = pattern.replace("\\", "/")
                expression = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
                flags = re.DOTALL | (re.IGNORECASE if os.name == "nt" else 0)
                if re.fullmatch(expression, path, flags=flags):
                    result = action
            return result

        cases = {
            "orchestrator-10-workflow-bootstrap.md": (
                [".gitignore", "ET.API.3/.gitignore", "services/ET.API.3/.gitignore", ".orchestrator/tasks/t/manifest.json", "ET.API.3/.orchestrator/tasks/t/contract.md", "services/ET.API.3/.orchestrator/tasks/t/requests/R001.md", ".orchestrator/tasks/t/baseline/index.json"],
                ["not.gitignore", "ET.API.3/not.gitignore", ".orchestrator/tasks/t/plan/master.md", ".orchestrator/tasks/t/reviews/mini/lanes/lane.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-20-planner.md": (
                [".orchestrator/tasks/t/recon/index.md", "ET.API.3/.orchestrator/tasks/t/plan/master.md", "services/ET.API.3/.orchestrator/tasks/t/plan/dispatch/S001.json", r"services\ET.API.3\.orchestrator\tasks\t\recon\index.md", ".orchestrator/tasks/t/stages/S001.md"],
                [".orchestrator/tasks/t/recon/other.md", ".orchestrator/tasks/t/plan/audit.md", ".orchestrator/tasks/t/recon/index.json", r"services\ET.API.3\.orchestrator\tasks\t\recon\index.json", "ET.API.3/Program.cs"],
            ),
            "orchestrator-25-planner-full.md": (
                [".orchestrator/tasks/t/recon/prototypes.md", "ET.API.3/.orchestrator/tasks/t/plan/master.md", "services/ET.API.3/.orchestrator/tasks/t/plan/audit.md", ".orchestrator/tasks/t/plan/structure.json"],
                [".orchestrator/tasks/t/plan/dispatch/S001.json", ".orchestrator/tasks/t/stages/S001.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-30-planner-senior.md": (
                [".orchestrator/tasks/t/plan/master.md", "ET.API.3/.orchestrator/tasks/t/plan/audit.md", "services/ET.API.3/.orchestrator/tasks/t/plan/structure.json"],
                [".orchestrator/tasks/t/plan/dispatch/S001.json", ".orchestrator/tasks/t/recon/index.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-50-validator.md": (
                [".orchestrator/tasks/t/validation/final/index.md", "services/ET.API.3/.orchestrator/tasks/t/snapshots/S001/manifest.json"],
                [".orchestrator/tasks/t/plan/master.md", ".orchestrator/tasks/t/reviews/final/verdict.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-60-mini-reviewer.md": (
                [".orchestrator/tasks/t/reviews/mini/lanes/goal.md", "services/ET.API.3/.orchestrator/tasks/t/reviews/mini/lanes/security.md"],
                [".orchestrator/tasks/t/reviews/mini/aggregate/index.md", ".orchestrator/tasks/t/reviews/final/verdict.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-70-review-aggregator.md": (
                [".orchestrator/tasks/t/reviews/mini/aggregate/index.md", "services/ET.API.3/.orchestrator/tasks/t/reviews/mini/aggregate/final.md"],
                [".orchestrator/tasks/t/reviews/mini/lanes/goal.md", ".orchestrator/tasks/t/reviews/final/verdict.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-80-final-reviewer.md": (
                [".orchestrator/tasks/t/reviews/final/verdict.md", "services/ET.API.3/.orchestrator/tasks/t/reviews/final/round-2.md"],
                [".orchestrator/tasks/t/reviews/mini/aggregate/index.md", ".orchestrator/tasks/t/reviews/final/verdict.json", "ET.API.3/Program.cs"],
            ),
        }

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(ROOT, target, "install")
            for filename, (allowed, denied) in cases.items():
                content = (target / "agents" / filename).read_text(encoding="utf-8")
                rules = permission_rules(content, "edit")
                self.assertEqual(rules[0], ("*", "deny"))
                for path in allowed:
                    self.assertEqual(evaluate(rules, path), "allow", f"{filename} should allow {path}")
                for path in denied:
                    self.assertEqual(evaluate(rules, path), "deny", f"{filename} should deny {path}")
                if os.name == "nt" and allowed:
                    self.assertEqual(evaluate(rules, allowed[0].upper()), "allow", f"{filename} should match case-insensitively on Windows")
            for filename in ("orchestrator-00-main.md", "orchestrator-01-single-model-main.md"):
                content = (target / "agents" / filename).read_text(encoding="utf-8")
                rules = permission_rules(content, "read")
                self.assertEqual(rules[0], ("*", "deny"))
                for path in (".orchestrator/tasks/t/manifest.json", "ET.API.3/.orchestrator/tasks/t/plan/master.md", "services/ET.API.3/.orchestrator/tasks/t/reviews/mini/aggregate/index.md"):
                    self.assertEqual(evaluate(rules, path), "allow", f"{filename} should allow {path}")
                for path in ("ET.API.3/Program.cs", ".orchestrator/other.md"):
                    self.assertEqual(evaluate(rules, path), "deny", f"{filename} should deny {path}")

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
