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

    def test_protocol_permissions_match_opencode_tool_patterns(self):
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
            for pattern, action in rules:
                regex = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
                if re.fullmatch(regex, path):
                    result = action
            return result

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(ROOT, target, "install")
            external_pattern = f"{target}/protocols/*"
            protocol_relative = "../../config/protocols/orchestrator-v2.md"
            sibling_relative = "../../config/protocols/other.md"
            for prompt in sorted((target / "agents").glob("orchestrator-*.md")):
                content = prompt.read_text(encoding="utf-8")
                external_rules = permission_rules(content, "external_directory")
                read_rules = permission_rules(content, "read")
                self.assertEqual(evaluate(external_rules, external_pattern), "allow", prompt.name)
                self.assertEqual(evaluate(external_rules, f"{target}/skills/*"), "deny", prompt.name)
                self.assertEqual(evaluate(read_rules, protocol_relative), "allow", prompt.name)
                self.assertEqual(evaluate(read_rules, sibling_relative), "deny", prompt.name)

    def test_rendered_workflow_enforces_dispatch_and_validation_gates(self):
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

        def evaluate(rules, command):
            result = "ask"
            for pattern, action in rules:
                expression = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
                if re.fullmatch(expression, command):
                    result = action
            return result

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(ROOT, target, "install")
            for filename in ("orchestrator-00-main.md", "orchestrator-01-single-model-main.md"):
                content = (target / "agents" / filename).read_text(encoding="utf-8")
                self.assertNotIn("explore: allow", content)
                self.assertIn("<dispatch_guard priority=\"critical\">", content)
                self.assertIn("never copy source bodies", content)
                self.assertIn("validator-produced `DISPATCH_AUTHORIZATION_ID`", content)
                self.assertIn("Only validator STAGE/FINAL output establishes a post-mutation product snapshot", content)
            executor = (target / "agents/orchestrator-40-executor.md").read_text(encoding="utf-8")
            self.assertIn("copied source bodies, inferred plans, and ad hoc write lists return `BLOCKED`", executor)
            self.assertIn("Direct Git command patterns and edit-tool `.git` writes are denied", executor)
            self.assertIn("Reject commands containing unquoted shell control operators", executor)
            self.assertEqual(evaluate(permission_rules(executor, "bash"), "git checkout -- file.cs"), "deny")
            self.assertEqual(evaluate(permission_rules(executor, "bash"), "dotnet test Tests.csproj"), "allow")
            self.assertEqual(evaluate(permission_rules(executor, "bash"), "dotnet test Digital.Tests.csproj"), "allow")
            self.assertEqual(evaluate(permission_rules(executor, "bash"), "/usr/bin/git status"), "deny")
            validator = (target / "agents/orchestrator-50-validator.md").read_text(encoding="utf-8")
            self.assertIn("reject unquoted shell control operators", validator)
            self.assertIn("every other Git command requires runtime user approval", validator)
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "/usr/bin/git restore file.cs"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git status --short"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "python3 tests/test-cli.py"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "dotnet test Digital.Tests.csproj"), "allow")
            protocol = (target / "protocols/orchestrator-v2.md").read_text(encoding="utf-8")
            executor_contract = "EXECUTOR_REPORT | <stage|repair> | PASS|FAIL|BLOCKED|DEVIATION|STALE | product: <paths|none> | expected-product: <ID> | authorization: <ID> | validation: PASS|FAIL|BLOCKED | evidence: <path|required for PASS> | blocker: <none|exact>"
            self.assertIn(executor_contract, executor)
            self.assertIn(executor_contract, protocol)

    def test_nested_workspace_workflow_root_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(ROOT, target, "install")
            primary = (target / "agents/orchestrator-00-main.md").read_text(encoding="utf-8")
            bootstrap = (target / "agents/orchestrator-10-workflow-bootstrap.md").read_text(encoding="utf-8")
            executor = (target / "agents/orchestrator-40-executor.md").read_text(encoding="utf-8")
            validator = (target / "agents/orchestrator-50-validator.md").read_text(encoding="utf-8")
            protocol = (target / "protocols/orchestrator-v2.md").read_text(encoding="utf-8")
            expected_root = "WORKSPACE_ROOT/.orchestrator/tasks/<workflow-id>"
            self.assertIn("active-session project directory", primary)
            self.assertIn(expected_root, primary)
            self.assertIn("Bootstrap `INITIALIZE` receives caller-derived exact absolute `WORKSPACE_ROOT`", primary)
            self.assertIn("every later role call, including bootstrap `APPEND_REQUEST`", primary)
            self.assertIn("stale identity or workflow root returns `STALE` without transition", primary)
            self.assertIn(expected_root, bootstrap)
            self.assertIn("validate them before manifest exists", bootstrap)
            self.assertIn("Git discovery records `GIT_REPOSITORY_ROOT` only", bootstrap)
            self.assertIn("<append_request>\nBefore writes, after normalized path comparison, require supplied absolute `WORKSPACE_ROOT` and `WORKFLOW_ROOT` equal their corresponding manifest fields", bootstrap)
            self.assertIn(expected_root, executor)
            self.assertIn(expected_root, validator)
            self.assertIn("never replaced by a different root found through Git discovery", protocol)
            self.assertIn("when it differs from `WORKSPACE_ROOT`", protocol)
            self.assertIn("relative artifact paths are valid only relative to that root, never Git root", protocol)
            for filename in ("orchestrator-20-planner.md", "orchestrator-25-planner-full.md", "orchestrator-30-planner-senior.md", "orchestrator-40-executor.md", "orchestrator-50-validator.md", "orchestrator-60-mini-reviewer.md", "orchestrator-70-review-aggregator.md", "orchestrator-80-final-reviewer.md"):
                content = (target / "agents" / filename).read_text(encoding="utf-8")
                self.assertIn("supplied absolute `WORKSPACE_ROOT` and `WORKFLOW_ROOT` equal their corresponding manifest fields", content, filename)
                self.assertIn(expected_root, content, filename)
                self.assertIn("Return `STALE`" if "planner" in filename else "returns `STALE`", content, filename)

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
            "orchestrator-40-executor.md": (
                ["Program.cs", ".orchestrator/tasks/t/stages/executor/D001/report.md", "services/ET.API.3/.orchestrator/tasks/t/stages/executor/D001/log.txt"],
                [".git", ".git/index", "services/ET.API.3/.git", "services/ET.API.3/.git/config", ".orchestrator/tasks/t/manifest.json", ".orchestrator/tasks/t/plan/master.md", "services/ET.API.3/.orchestrator/tasks/t/reviews/mini/aggregate/index.md"],
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
                self.assertEqual(rules[0], ("*", "allow") if filename == "orchestrator-40-executor.md" else ("*", "deny"))
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
