import subprocess
import sys
import tempfile
import unittest
import os
import importlib.util
import base64
import hashlib
import json
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
CHECKPOINT_SPEC = importlib.util.spec_from_file_location("opencode_checkpoint", ROOT / "helpers/checkpoint.py")
if CHECKPOINT_SPEC is None or CHECKPOINT_SPEC.loader is None:
    raise RuntimeError("cannot load helpers/checkpoint.py")
OPENCODE_CHECKPOINT = importlib.util.module_from_spec(CHECKPOINT_SPEC)
CHECKPOINT_SPEC.loader.exec_module(OPENCODE_CHECKPOINT)


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
            self.assertEqual(len(prompts), 13)
            for prompt in prompts:
                content = prompt.read_text(encoding="utf-8")
                self.assertNotIn("__OPENCODE_PROTOCOL_PATH_", content)
                self.assertNotIn("__OPENCODE_HELPER_DIRECTORY_PATH_", content)
                self.assertIn(str(target / "protocols/orchestrator-v2.md"), content)
            self.assertEqual([prompt.name for prompt in prompts], ["orchestrator-00-main.md", "orchestrator-01-single-model-main.md", "orchestrator-10-workflow-bootstrap.md", "orchestrator-20-planner.md", "orchestrator-25-planner-full.md", "orchestrator-30-planner-senior.md", "orchestrator-40-executor.md", "orchestrator-45-checkpointer.md", "orchestrator-50-validator.md", "orchestrator-60-mini-reviewer.md", "orchestrator-70-review-aggregator.md", "orchestrator-75-escalation-reviewer.md", "orchestrator-80-final-reviewer.md"])
            self.assertIn("name: orchestrator", (target / "agents/orchestrator-00-main.md").read_text(encoding="utf-8"))
            single_model = (target / "agents/orchestrator-01-single-model-main.md").read_text(encoding="utf-8")
            self.assertIn("name: orchestrator-single-model", single_model)
            self.assertIn("WORKFLOW_PROFILE: SINGLE_MODEL", single_model)
            self.assertNotIn("orchestrator-30-planner-senior", single_model)
            self.assertNotIn("orchestrator-75-escalation-reviewer: allow", single_model)
            self.assertNotIn("orchestrator-80-final-reviewer", single_model)
            self.assertNotIn("\nmodel:", single_model)
            self.assertNotIn("\nmodel:", (target / "agents/orchestrator-25-planner-full.md").read_text(encoding="utf-8"))
            self.assertNotIn("Load `caveman`", (target / "agents/orchestrator-00-main.md").read_text(encoding="utf-8"))
            self.assertIn("caveman` skill is available", (target / "agents/orchestrator-40-executor.md").read_text(encoding="utf-8"))
            escalation = (target / "agents/orchestrator-75-escalation-reviewer.md").read_text(encoding="utf-8")
            self.assertIn("model: openai/gpt-5.6-terra", escalation)
            self.assertIn("Do not search speculatively", escalation)
            self.assertIn("PREPARE_MINI_REVIEW", (target / "agents/orchestrator-50-validator.md").read_text(encoding="utf-8"))
            checkpointer = (target / "agents/orchestrator-45-checkpointer.md").read_text(encoding="utf-8")
            self.assertNotIn("__OPENCODE_CHECKPOINT_HELPER_PATH_", checkpointer)
            self.assertIn(str(target / "helpers/checkpoint.py"), checkpointer)
            self.assertTrue((target / "helpers/checkpoint.py").is_file())
            self.assertIn("Never amend, squash, merge, reset", checkpointer)

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
                if prompt.name in ("orchestrator-45-checkpointer.md", "orchestrator-50-validator.md"):
                    self.assertEqual(evaluate(external_rules, f"{target}/helpers/*"), "allow", prompt.name)
                else:
                    self.assertEqual(evaluate(external_rules, f"{target}/helpers/*"), "deny", prompt.name)
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
            self.assertIn("status.md", content)
            executor = (target / "agents/orchestrator-40-executor.md").read_text(encoding="utf-8")
            self.assertIn("copied source bodies, inferred plans, and ad hoc write lists return `BLOCKED`", executor)
            self.assertIn("Direct Git command patterns and edit-tool `.git` writes are denied", executor)
            self.assertIn("Reject commands containing unquoted shell control operators", executor)
            self.assertEqual(evaluate(permission_rules(executor, "bash"), "git checkout -- file.cs"), "deny")
            self.assertEqual(evaluate(permission_rules(executor, "bash"), "dotnet test Tests.csproj"), "allow")
            self.assertEqual(evaluate(permission_rules(executor, "bash"), "dotnet test Digital.Tests.csproj"), "allow")
            self.assertEqual(evaluate(permission_rules(executor, "bash"), "/usr/bin/git status"), "deny")
            checkpointer = (target / "agents/orchestrator-45-checkpointer.md").read_text(encoding="utf-8")
            helper = target / "helpers/checkpoint.py"
            helper_command = OPENCODE_AGENTS.checkpoint_commands(str(helper))[0]
            self.assertEqual(evaluate(permission_rules(checkpointer, "bash"), helper_command), "allow")
            self.assertEqual(evaluate(permission_rules(checkpointer, "bash"), f"{helper_command} --manifest unsafe"), "deny")
            self.assertEqual(evaluate(permission_rules(checkpointer, "bash"), "git add --all"), "deny")
            self.assertEqual(evaluate(permission_rules(checkpointer, "bash"), "git reset --mixed HEAD~1"), "deny")
            self.assertEqual(evaluate(permission_rules(checkpointer, "bash"), "git rebase main"), "deny")
            validator = (target / "agents/orchestrator-50-validator.md").read_text(encoding="utf-8")
            self.assertIn("reject unquoted shell control operators", validator)
            self.assertIn("every other Git command requires runtime user approval", validator)
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "/usr/bin/git restore file.cs"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git status --short --untracked-files=all"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git status --branch --short"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git status --porcelain=v1 --untracked-files=all"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git rev-parse --abbrev-ref HEAD"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git rev-parse HEAD^{tree}"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git rev-parse HEAD^"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff --name-status HEAD"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff --cached --name-status"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git ls-files --stage"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git for-each-ref --format='%(refname) %(objectname)'"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff --no-ext-diff --no-textconv --binary"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff --binary"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff HEAD"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff --name-status --patch HEAD"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff --name-status --textconv HEAD"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git status --short; git reset --hard"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git status --porcelain=v1 --untracked-files=all && git diff --name-status HEAD"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git for-each-ref --format='%(refname) %(objectname)' | wc -l"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff --textconv HEAD"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff --output=report.diff"), "deny")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff --output report.diff"), "deny")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff -o report.diff"), "deny")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git diff --name-status --output report.diff"), "deny")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git symbolic-ref -d refs/heads/main"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git symbolic-ref refs/heads/current refs/heads/main"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "git -c diff.external=/bin/false diff --ext-diff"), "ask")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "python3 tests/test-cli.py"), "allow")
            self.assertEqual(evaluate(permission_rules(validator, "bash"), "dotnet test Digital.Tests.csproj"), "allow")
            protocol = (target / "protocols/orchestrator-v2.md").read_text(encoding="utf-8")
            executor_contract = "EXECUTOR_REPORT | <stage|repair> | PASS|FAIL|BLOCKED|DEVIATION|STALE | product: <paths|none> | expected-product: <ID> | authorization: <ID> | validation: PASS|FAIL|BLOCKED | evidence: <path|required for PASS> | blocker: <none|exact>"
            self.assertIn(executor_contract, executor)
            self.assertIn(executor_contract, protocol)
            self.assertIn("Orchestrator Protocol v3", protocol)
            self.assertIn("REVIEW_EPOCH_ID", protocol)
            self.assertIn("CHECKPOINT_COMMIT_ID", protocol)
            self.assertIn("Raw `plan/master.md` and dispatch-file hashes may therefore change during activation", protocol)
            self.assertIn("canonical authorization-payload hash", validator)
            self.assertIn("Raw pre-activation dispatch or plan-file hash differences alone are expected", executor)

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
            for filename in ("orchestrator-20-planner.md", "orchestrator-25-planner-full.md", "orchestrator-30-planner-senior.md", "orchestrator-40-executor.md", "orchestrator-45-checkpointer.md", "orchestrator-50-validator.md", "orchestrator-60-mini-reviewer.md", "orchestrator-70-review-aggregator.md", "orchestrator-75-escalation-reviewer.md", "orchestrator-80-final-reviewer.md"):
                content = (target / "agents" / filename).read_text(encoding="utf-8")
                self.assertIn("supplied absolute `WORKSPACE_ROOT` and `WORKFLOW_ROOT` equal their corresponding manifest fields", content, filename)
                self.assertIn(expected_root, content, filename)
                self.assertIn("Return `STALE`" if "planner" in filename else "returns `STALE`", content, filename)

    def test_v3_state_transitions_are_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(ROOT, target, "install")
            primary = (target / "agents/orchestrator-00-main.md").read_text(encoding="utf-8")
            planner = (target / "agents/orchestrator-20-planner.md").read_text(encoding="utf-8")
            validator = (target / "agents/orchestrator-50-validator.md").read_text(encoding="utf-8")
            escalation = (target / "agents/orchestrator-75-escalation-reviewer.md").read_text(encoding="utf-8")
            single_model = (target / "agents/orchestrator-01-single-model-main.md").read_text(encoding="utf-8")
            for mode in ("MINI_REVIEW_RESULT", "ESCALATION_RESULT", "CHECKPOINT_RESULT", "FINAL_VALIDATION_RESULT", "FINAL_MINI_RESULT", "START_FINAL_CYCLE"):
                self.assertIn(f"`{mode}`", primary)
                self.assertIn(f"`{mode}`", planner)
            self.assertIn("prior Terra-directed replan/repair", escalation)
            self.assertNotIn("orchestrator-75-escalation-reviewer: allow", single_model)
            self.assertIn("without numeric limit", single_model)
            self.assertIn("OPERATIONAL_CONSENT_REQUIRED", primary)

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
                [".gitignore", "ET.API.3/.gitignore", "services/ET.API.3/.gitignore", ".orchestrator/tasks/t/manifest.json", "ET.API.3/.orchestrator/tasks/t/contract.md", "services/ET.API.3/.orchestrator/tasks/t/requests/R001.md", ".orchestrator/tasks/t/baseline/index.json", "ET.API.3/.orchestrator/tasks/t/status.md"],
                ["not.gitignore", "ET.API.3/not.gitignore", ".orchestrator/tasks/t/plan/master.md", ".orchestrator/tasks/t/reviews/mini/lanes/lane.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-20-planner.md": (
                [".orchestrator/tasks/t/recon/index.md", "ET.API.3/.orchestrator/tasks/t/plan/master.md", "services/ET.API.3/.orchestrator/tasks/t/plan/dispatch/S001.json", r"services\ET.API.3\.orchestrator\tasks\t\recon\index.md", ".orchestrator/tasks/t/stages/S001.md", "ET.API.3/.orchestrator/tasks/t/status.md"],
                [".orchestrator/tasks/t/recon/other.md", ".orchestrator/tasks/t/plan/audit.md", ".orchestrator/tasks/t/recon/index.json", r"services\ET.API.3\.orchestrator\tasks\t\recon\index.json", "ET.API.3/Program.cs"],
            ),
            "orchestrator-25-planner-full.md": (
                [".orchestrator/tasks/t/recon/prototypes.md", "ET.API.3/.orchestrator/tasks/t/plan/master.md", "services/ET.API.3/.orchestrator/tasks/t/plan/audit.md", ".orchestrator/tasks/t/plan/structure.json", ".orchestrator/tasks/t/status.md", "ET.API.3/.orchestrator/tasks/t/status.md"],
                [".orchestrator/tasks/t/plan/dispatch/S001.json", ".orchestrator/tasks/t/stages/S001.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-30-planner-senior.md": (
                [".orchestrator/tasks/t/plan/master.md", "ET.API.3/.orchestrator/tasks/t/plan/audit.md", "services/ET.API.3/.orchestrator/tasks/t/plan/structure.json", ".orchestrator/tasks/t/status.md", "ET.API.3/.orchestrator/tasks/t/status.md"],
                [".orchestrator/tasks/t/plan/dispatch/S001.json", ".orchestrator/tasks/t/recon/index.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-50-validator.md": (
                [".orchestrator/tasks/t/validation/final/index.md", "services/ET.API.3/.orchestrator/tasks/t/snapshots/S001/manifest.json"],
                [".orchestrator/tasks/t/plan/master.md", ".orchestrator/tasks/t/reviews/final/verdict.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-45-checkpointer.md": (
                [".orchestrator/checkpoint-active.json", "ET.API.3/.orchestrator/checkpoint-active.json", ".orchestrator/tasks/t/snapshots/S001/manifest.json", "services/ET.API.3/.orchestrator/tasks/t/snapshots/S001/checkpoint.md"],
                [".orchestrator/tasks/t/plan/master.md", ".orchestrator/tasks/t/reviews/final/verdict.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-40-executor.md": (
                ["Program.cs", ".orchestrator/tasks/t/stages/executor/D001/report.md", "services/ET.API.3/.orchestrator/tasks/t/stages/executor/D001/log.txt"],
                [".git", ".git/index", "services/ET.API.3/.git", "services/ET.API.3/.git/config", ".orchestrator/tasks/t/manifest.json", ".orchestrator/tasks/t/plan/master.md", "services/ET.API.3/.orchestrator/tasks/t/reviews/mini/aggregate/index.md"],
            ),
            "orchestrator-60-mini-reviewer.md": (
                [".orchestrator/tasks/t/reviews/mini/epochs/E1/lanes/goal.md", "services/ET.API.3/.orchestrator/tasks/t/reviews/mini/epochs/E1/lanes/security.md"],
                [".orchestrator/tasks/t/reviews/mini/aggregate/index.md", ".orchestrator/tasks/t/reviews/final/verdict.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-70-review-aggregator.md": (
                [".orchestrator/tasks/t/reviews/mini/epochs/E1/aggregate.md", "services/ET.API.3/.orchestrator/tasks/t/reviews/mini/epochs/E2/aggregate.md"],
                [".orchestrator/tasks/t/reviews/mini/lanes/goal.md", ".orchestrator/tasks/t/reviews/final/verdict.md", "ET.API.3/Program.cs"],
            ),
            "orchestrator-75-escalation-reviewer.md": (
                [".orchestrator/tasks/t/reviews/escalation/E1.md", "services/ET.API.3/.orchestrator/tasks/t/reviews/escalation/E2.md"],
                [".orchestrator/tasks/t/reviews/mini/epochs/E1/aggregate.md", ".orchestrator/tasks/t/reviews/final/verdict.md", "ET.API.3/Program.cs"],
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

    def test_checkpoint_command_rendering_handles_special_target_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config with ' quote"
            self.run_cli(ROOT, target, "install")
            checkpointer = (target / "agents/orchestrator-45-checkpointer.md").read_text(encoding="utf-8")
            command = OPENCODE_AGENTS.checkpoint_commands(str(target / "helpers/checkpoint.py"))[0]
            self.assertIn(json.dumps(command, ensure_ascii=False), checkpointer)
            self.assertNotIn("__OPENCODE_CHECKPOINT_", checkpointer)

    def test_windows_checkpoint_command_quotes_shell_metacharacters(self):
        helper = r"C:\cfg&prod^(x)|y<z>\helpers\checkpoint.py"
        with patch.object(OPENCODE_AGENTS.os, "name", "nt"):
            python3_command, py_command = OPENCODE_AGENTS.checkpoint_commands(helper)
            self.assertEqual(python3_command, f'python3 "{helper}"')
            self.assertEqual(py_command, f'py -3 "{helper}"')
            with self.assertRaisesRegex(RuntimeError, "unsupported Windows shell character"):
                OPENCODE_AGENTS.checkpoint_commands(r"C:\cfg%TEMP%\checkpoint.py")
            with self.assertRaisesRegex(RuntimeError, "unsupported Windows shell character"):
                OPENCODE_AGENTS.checkpoint_commands(r"C:\cfg$(Get-Item x)\checkpoint.py")
        with self.assertRaisesRegex(RuntimeError, "unsupported permission-pattern character"):
            OPENCODE_AGENTS.checkpoint_commands("/tmp/config*/helpers/checkpoint.py")

    def test_checkpoint_helper_commits_exact_paths_and_preserves_user_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / ".gitattributes").write_text("*.txt text eol=lf\n", encoding="utf-8")
            (root / "changed.txt").write_text("before\n", encoding="utf-8")
            (root / "deleted.txt").write_text("delete me\n", encoding="utf-8")
            (root / "user.txt").write_text("user before\n", encoding="utf-8")
            self.git(root, "add", ".gitignore", ".gitattributes", "changed.txt", "deleted.txt", "user.txt")
            self.git(root, "commit", "-qm", "baseline")
            parent = self.git(root, "rev-parse", "HEAD", capture_output=True).stdout.strip()
            branch = self.git(root, "symbolic-ref", "-q", "HEAD", capture_output=True).stdout.strip()
            (root / "user.txt").write_text("user staged\n", encoding="utf-8")
            self.git(root, "add", "user.txt")
            (root / "changed.txt").write_bytes(b"after\r\n")
            (root / "deleted.txt").unlink()
            (root / "new.txt").write_text("new\n", encoding="utf-8")
            requests = root / ".orchestrator" / "tasks" / "workflow" / "snapshots" / "checkpoint-requests"
            requests.mkdir(parents=True)
            request = {
                "schema": "orchestrator-checkpoint-v1",
                "checkpoint_request_id": "WP1",
                "supersedes": [],
                "state": "READY",
                "purpose": "STAGE",
                "workspace_root": str(root),
                "workflow_root": str(root / ".orchestrator" / "tasks" / "workflow"),
                "git_repository_root": str(root),
                "expected_head": parent,
                "expected_branch_ref": branch,
                "stage": "WP1",
                "declared_paths": ["changed.txt", "deleted.txt", "new.txt"],
                "declared_path_states": {path: OPENCODE_CHECKPOINT.path_state(root, path) for path in ("changed.txt", "deleted.txt", "new.txt")},
                "declared_git_states": {path: OPENCODE_CHECKPOINT.git_state(root, root, path) for path in ("changed.txt", "deleted.txt", "new.txt")},
                "baseline_user_paths": ["user.txt"],
                "reviewed_index_digest": OPENCODE_CHECKPOINT.index_digest(OPENCODE_CHECKPOINT.index_entries(root), set()),
                "product_snapshot_id": "a" * 64,
                "review_epoch_id": "b" * 64,
                "plan_structure_id": "c" * 64,
                "subject": "checkpoint WP1",
            }
            request_path = requests / "WP1.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            self.write_checkpoint_pointer(root, request_path)

            result = OPENCODE_CHECKPOINT.checkpoint(root)

            self.assertEqual(result["parent"], parent)
            self.assertRegex(result["tree"], r"^[0-9a-f]{40,64}$")
            self.assertRegex(result["checkpoint_commit_id"], r"^[0-9a-f]{64}$")
            committed = self.git(root, "show", "--name-only", "--format=", "HEAD", capture_output=True).stdout.split()
            self.assertEqual(set(committed), {"changed.txt", "deleted.txt", "new.txt"})
            self.assertEqual(self.git(root, "diff", "--name-only", capture_output=True).stdout, "")
            self.assertEqual(self.git(root, "diff", "--cached", "--name-only", capture_output=True).stdout.strip(), "user.txt")
            self.assertEqual(self.git(root, "status", "--short", capture_output=True).stdout.strip(), "M  user.txt")
            (root / "changed.txt").write_text("second stage\n", encoding="utf-8")
            self.write_checkpoint_request(root, root, "WP2", ["changed.txt"], ["user.txt"])
            wp2 = OPENCODE_CHECKPOINT.checkpoint(root)
            self.assertEqual(self.git(root, "rev-list", "--count", "HEAD", capture_output=True).stdout.strip(), "3")
            replay = OPENCODE_CHECKPOINT.checkpoint(root)
            self.assertEqual(replay["commit"], wp2["commit"])
            self.assertEqual(self.git(root, "rev-list", "--count", "HEAD", capture_output=True).stdout.strip(), "3")
            foreign_lock = root / self.git(root, "rev-parse", "--git-path", "index.lock", capture_output=True).stdout.strip()
            foreign_lock.write_bytes(b"foreign")
            with self.assertRaisesRegex(OPENCODE_CHECKPOINT.CheckpointError, "repository index is locked by another process"):
                OPENCODE_CHECKPOINT.checkpoint(root)
            self.assertEqual(foreign_lock.read_bytes(), b"foreign")

    def test_checkpoint_helper_commits_bootstrap_setup_with_first_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / "file.txt").write_text("before\n", encoding="utf-8")
            self.git(root, "add", "file.txt")
            self.git(root, "commit", "-qm", "baseline")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / "file.txt").write_text("after\n", encoding="utf-8")
            self.write_checkpoint_request(root, root, "WP1", [".gitignore", "file.txt"], [])

            OPENCODE_CHECKPOINT.checkpoint(root)

            committed = self.git(root, "show", "--name-only", "--format=", "HEAD", capture_output=True).stdout.split()
            self.assertEqual(committed, [".gitignore", "file.txt"])

    def test_checkpoint_helper_rejects_user_path_overlap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / "same.txt").write_text("before\n", encoding="utf-8")
            self.git(root, "add", ".gitignore", "same.txt")
            self.git(root, "commit", "-qm", "baseline")
            requests = root / ".orchestrator" / "tasks" / "workflow" / "snapshots" / "checkpoint-requests"
            requests.mkdir(parents=True)
            request = {
                "schema": "orchestrator-checkpoint-v1",
                "checkpoint_request_id": "WP1",
                "supersedes": [],
                "state": "READY",
                "purpose": "STAGE",
                "workspace_root": str(root),
                "workflow_root": str(root / ".orchestrator" / "tasks" / "workflow"),
                "git_repository_root": str(root),
                "expected_head": self.git(root, "rev-parse", "HEAD", capture_output=True).stdout.strip(),
                "expected_branch_ref": self.git(root, "symbolic-ref", "-q", "HEAD", capture_output=True).stdout.strip(),
                "stage": "WP1",
                "declared_paths": ["same.txt"],
                "declared_path_states": {"same.txt": OPENCODE_CHECKPOINT.path_state(root, "same.txt")},
                "declared_git_states": {"same.txt": OPENCODE_CHECKPOINT.git_state(root, root, "same.txt")},
                "baseline_user_paths": ["same.txt"],
                "reviewed_index_digest": OPENCODE_CHECKPOINT.index_digest(OPENCODE_CHECKPOINT.index_entries(root), set()),
                "product_snapshot_id": "a" * 64,
                "review_epoch_id": "b" * 64,
                "plan_structure_id": "c" * 64,
                "subject": "checkpoint WP1",
            }
            request_path = requests / "WP1.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            self.write_checkpoint_pointer(root, request_path)

            with self.assertRaisesRegex(OPENCODE_CHECKPOINT.CheckpointError, "overlap"):
                OPENCODE_CHECKPOINT.checkpoint(root)

    def test_checkpoint_helper_rejects_changed_head(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / "file.txt").write_text("before\n", encoding="utf-8")
            self.git(root, "add", ".gitignore", "file.txt")
            self.git(root, "commit", "-qm", "baseline")
            branch = self.git(root, "symbolic-ref", "-q", "HEAD", capture_output=True).stdout.strip()
            (root / "file.txt").write_text("after\n", encoding="utf-8")
            requests = root / ".orchestrator" / "tasks" / "workflow" / "snapshots" / "checkpoint-requests"
            requests.mkdir(parents=True)
            request = {
                "schema": "orchestrator-checkpoint-v1",
                "checkpoint_request_id": "WP1",
                "supersedes": [],
                "state": "READY",
                "purpose": "STAGE",
                "workspace_root": str(root),
                "workflow_root": str(root / ".orchestrator" / "tasks" / "workflow"),
                "git_repository_root": str(root),
                "expected_head": "0" * 40,
                "expected_branch_ref": branch,
                "stage": "WP1",
                "declared_paths": ["file.txt"],
                "declared_path_states": {"file.txt": OPENCODE_CHECKPOINT.path_state(root, "file.txt")},
                "declared_git_states": {"file.txt": OPENCODE_CHECKPOINT.git_state(root, root, "file.txt")},
                "baseline_user_paths": [],
                "reviewed_index_digest": OPENCODE_CHECKPOINT.index_digest(OPENCODE_CHECKPOINT.index_entries(root), set()),
                "product_snapshot_id": "a" * 64,
                "review_epoch_id": "b" * 64,
                "plan_structure_id": "c" * 64,
                "subject": "checkpoint WP1",
            }
            request_path = requests / "WP1.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            self.write_checkpoint_pointer(root, request_path)

            with self.assertRaisesRegex(OPENCODE_CHECKPOINT.CheckpointError, "checkpoint commit exists|parent mismatch"):
                OPENCODE_CHECKPOINT.checkpoint(root)

    def test_checkpoint_helper_supports_nested_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            git_root = Path(temporary).resolve()
            workspace = git_root / "nested"
            workspace.mkdir()
            self.git(git_root, "init", "-q")
            self.git(git_root, "config", "user.name", "Checkpoint Test")
            self.git(git_root, "config", "user.email", "checkpoint@example.invalid")
            (git_root / ".gitignore").write_text("/nested/.orchestrator/\n", encoding="utf-8")
            (workspace / "file.txt").write_text("before\n", encoding="utf-8")
            self.git(git_root, "add", ".gitignore", "nested/file.txt")
            self.git(git_root, "commit", "-qm", "baseline")
            (workspace / "file.txt").write_text("after\n", encoding="utf-8")
            self.write_checkpoint_request(workspace, git_root, "WP1", ["file.txt"], [])

            OPENCODE_CHECKPOINT.checkpoint(workspace)

            committed = self.git(git_root, "show", "--name-only", "--format=", "HEAD", capture_output=True).stdout.split()
            self.assertEqual(committed, ["nested/file.txt"])
            self.assertEqual(self.git(git_root, "status", "--short", capture_output=True).stdout, "")

    def test_checkpoint_helper_rejects_post_review_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / "file.txt").write_text("before\n", encoding="utf-8")
            self.git(root, "add", ".gitignore", "file.txt")
            self.git(root, "commit", "-qm", "baseline")
            (root / "file.txt").write_text("reviewed\n", encoding="utf-8")
            self.write_checkpoint_request(root, root, "WP1", ["file.txt"], [])
            expected_head = self.git(root, "rev-parse", "HEAD", capture_output=True).stdout.strip()
            (root / "file.txt").write_text("changed after review\n", encoding="utf-8")

            with self.assertRaisesRegex(OPENCODE_CHECKPOINT.CheckpointError, "reviewed path state changed"):
                OPENCODE_CHECKPOINT.checkpoint(root)
            self.assertEqual(self.git(root, "rev-parse", "HEAD", capture_output=True).stdout.strip(), expected_head)

    def test_checkpoint_helper_rejects_post_review_index_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / "file.txt").write_text("before\n", encoding="utf-8")
            self.git(root, "add", ".gitignore", "file.txt")
            self.git(root, "commit", "-qm", "baseline")
            (root / "file.txt").write_text("reviewed\n", encoding="utf-8")
            self.write_checkpoint_request(root, root, "WP1", ["file.txt"], [])
            self.git(root, "add", "file.txt")

            with self.assertRaisesRegex(OPENCODE_CHECKPOINT.CheckpointError, "repository index changed after review"):
                OPENCODE_CHECKPOINT.checkpoint(root)

    def test_checkpoint_index_digest_includes_every_conflict_stage(self):
        entries = {
            ("file.txt", "1"): b"100644 " + b"1" * 40 + b" 1",
            ("file.txt", "2"): b"100644 " + b"2" * 40 + b" 2",
            ("file.txt", "3"): b"100644 " + b"3" * 40 + b" 3",
        }
        without_ours = dict(entries)
        del without_ours[("file.txt", "2")]

        self.assertNotEqual(OPENCODE_CHECKPOINT.index_digest(entries, set()), OPENCODE_CHECKPOINT.index_digest(without_ours, set()))

    @unittest.skipIf(os.name == "nt", "Git pathspec-magic filename is not valid on Windows")
    def test_checkpoint_helper_treats_declared_paths_literally(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / ":(top)evil.txt").write_text("before\n", encoding="utf-8")
            (root / "evil.txt").write_text("user before\n", encoding="utf-8")
            self.git(root, "add", ".gitignore", ":(literal):(top)evil.txt", "evil.txt")
            self.git(root, "commit", "-qm", "baseline")
            (root / ":(top)evil.txt").write_text("after\n", encoding="utf-8")
            (root / "evil.txt").write_text("user staged\n", encoding="utf-8")
            self.git(root, "add", "evil.txt")
            self.write_checkpoint_request(root, root, "WP1", [":(top)evil.txt"], ["evil.txt"])

            OPENCODE_CHECKPOINT.checkpoint(root)

            committed = self.git(root, "show", "--name-only", "--format=", "HEAD", capture_output=True).stdout.split()
            self.assertEqual(committed, [":(top)evil.txt"])
            self.assertEqual(self.git(root, "diff", "--cached", "--name-only", capture_output=True).stdout.strip(), "evil.txt")

    def test_checkpoint_helper_recovers_after_result_write_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / "file.txt").write_text("before\n", encoding="utf-8")
            self.git(root, "add", ".gitignore", "file.txt")
            self.git(root, "commit", "-qm", "baseline")
            (root / "file.txt").write_text("after\n", encoding="utf-8")
            self.write_checkpoint_request(root, root, "WP1", ["file.txt"], [])
            original_atomic_json = OPENCODE_CHECKPOINT.atomic_json
            failed = {"value": False}

            def fail_result_once(workspace_root, path, payload):
                if path.name.startswith("checkpoint-WP1-") and not failed["value"]:
                    failed["value"] = True
                    raise OSError("injected result failure")
                return original_atomic_json(workspace_root, path, payload)

            with patch.object(OPENCODE_CHECKPOINT, "atomic_json", side_effect=fail_result_once):
                with self.assertRaisesRegex(OSError, "injected result failure"):
                    OPENCODE_CHECKPOINT.checkpoint(root)
            committed_head = self.git(root, "rev-parse", "HEAD", capture_output=True).stdout.strip()

            result = OPENCODE_CHECKPOINT.checkpoint(root)

            self.assertEqual(result["commit"], committed_head)
            self.assertEqual(self.git(root, "rev-list", "--count", "HEAD", capture_output=True).stdout.strip(), "2")

    def test_checkpoint_helper_ref_failure_preserves_real_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / "workflow.txt").write_text("before\n", encoding="utf-8")
            (root / "user.txt").write_text("user before\n", encoding="utf-8")
            self.git(root, "add", ".gitignore", "workflow.txt", "user.txt")
            self.git(root, "commit", "-qm", "baseline")
            (root / "workflow.txt").write_text("after\n", encoding="utf-8")
            (root / "user.txt").write_text("user staged\n", encoding="utf-8")
            self.git(root, "add", "user.txt")
            self.write_checkpoint_request(root, root, "WP1", ["workflow.txt"], ["user.txt"])
            expected_head = self.git(root, "rev-parse", "HEAD", capture_output=True).stdout.strip()
            index_path = Path(self.git(root, "rev-parse", "--git-path", "index", capture_output=True).stdout.strip())
            if not index_path.is_absolute():
                index_path = root / index_path
            original_index = index_path.read_bytes()
            original_git = OPENCODE_CHECKPOINT.git

            def fail_ref(root_path, *arguments, **kwargs):
                if arguments and arguments[0] == "update-ref":
                    raise OPENCODE_CHECKPOINT.CheckpointError("injected ref failure")
                return original_git(root_path, *arguments, **kwargs)

            with patch.object(OPENCODE_CHECKPOINT, "git", side_effect=fail_ref):
                with self.assertRaisesRegex(OPENCODE_CHECKPOINT.CheckpointError, "injected ref failure"):
                    OPENCODE_CHECKPOINT.checkpoint(root)

            self.assertEqual(self.git(root, "rev-parse", "HEAD", capture_output=True).stdout.strip(), expected_head)
            self.assertEqual(index_path.read_bytes(), original_index)
            self.assertFalse(index_path.with_name(f"{index_path.name}.lock").exists())

    def test_checkpoint_helper_recovers_after_index_replace_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / "file.txt").write_text("before\n", encoding="utf-8")
            self.git(root, "add", ".gitignore", "file.txt")
            self.git(root, "commit", "-qm", "baseline")
            (root / "file.txt").write_text("after\n", encoding="utf-8")
            self.write_checkpoint_request(root, root, "WP1", ["file.txt"], [])
            original_replace = OPENCODE_CHECKPOINT.os.replace
            failed = {"value": False}

            def fail_index_replace(source, destination):
                if Path(source).name == "index.lock" and Path(destination).name == "index" and not failed["value"]:
                    failed["value"] = True
                    raise OSError("injected index replace failure")
                return original_replace(source, destination)

            with patch.object(OPENCODE_CHECKPOINT.os, "replace", side_effect=fail_index_replace):
                with self.assertRaisesRegex(OSError, "injected index replace failure"):
                    OPENCODE_CHECKPOINT.checkpoint(root)
            committed_head = self.git(root, "rev-parse", "HEAD", capture_output=True).stdout.strip()

            result = OPENCODE_CHECKPOINT.checkpoint(root)

            self.assertEqual(result["commit"], committed_head)
            self.assertEqual(self.git(root, "status", "--short", capture_output=True).stdout, "")

    def test_checkpoint_helper_cleans_validated_orphaned_pre_cas_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index_path = root / "index"
            lock_path = root / "index.lock"
            metadata_path = root / "index.lock.orchestrator.json"
            index_path.write_bytes(b"old-index")
            lock_path.write_bytes(b"prepared-index")
            metadata = {
                "schema": "orchestrator-index-lock-v1",
                "pid": 999999999,
                "request_id": "WP1",
                "expected_head": "a" * 40,
                "index_sha256": hashlib.sha256(b"prepared-index").hexdigest(),
            }
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            OPENCODE_CHECKPOINT.recover_orchestrator_index_lock(index_path, "a" * 40, "a" * 40, "WP1")

            self.assertFalse(lock_path.exists())
            self.assertFalse(metadata_path.exists())
            self.assertEqual(index_path.read_bytes(), b"old-index")

    def test_checkpoint_helper_preserves_foreign_lock_with_malformed_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index_path = root / "index"
            lock_path = root / "index.lock"
            metadata_path = root / "index.lock.orchestrator.json"
            index_path.write_bytes(b"old-index")
            lock_path.write_bytes(b"foreign-index")
            metadata = {
                "pid": 999999999,
                "request_id": "WP1",
                "expected_head": "a" * 40,
                "index_sha256": hashlib.sha256(b"foreign-index").hexdigest(),
            }
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            with self.assertRaisesRegex(OPENCODE_CHECKPOINT.CheckpointError, "invalid checkpoint index-lock metadata fields"):
                OPENCODE_CHECKPOINT.recover_orchestrator_index_lock(index_path, "a" * 40, "a" * 40, "WP1")

            self.assertEqual(lock_path.read_bytes(), b"foreign-index")
            self.assertTrue(metadata_path.exists())
            metadata_path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(OPENCODE_CHECKPOINT.CheckpointError, "invalid checkpoint index-lock metadata fields"):
                OPENCODE_CHECKPOINT.recover_orchestrator_index_lock(index_path, "a" * 40, "a" * 40, "WP1")

            self.assertEqual(lock_path.read_bytes(), b"foreign-index")
            self.assertTrue(metadata_path.exists())

    def test_checkpoint_helper_rejects_non_object_pointer_and_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            pointer_path = root / ".orchestrator" / "checkpoint-active.json"
            pointer_path.parent.mkdir(parents=True)
            pointer_path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(OPENCODE_CHECKPOINT.CheckpointError, "invalid active checkpoint pointer"):
                OPENCODE_CHECKPOINT.request_file(root)

            request_path = root / ".orchestrator" / "tasks" / "workflow" / "snapshots" / "checkpoint-requests" / "WP1.json"
            request_path.parent.mkdir(parents=True)
            request_path.write_text("[]", encoding="utf-8")
            self.write_checkpoint_pointer(root, request_path)

            with self.assertRaisesRegex(OPENCODE_CHECKPOINT.CheckpointError, "invalid checkpoint request"):
                OPENCODE_CHECKPOINT.request_file(root)

    def test_checkpoint_helper_selects_superseding_ready_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / "file.txt").write_text("before\n", encoding="utf-8")
            self.git(root, "add", ".gitignore", "file.txt")
            self.git(root, "commit", "-qm", "baseline")
            (root / "file.txt").write_text("after\n", encoding="utf-8")
            old_path = self.write_checkpoint_request(root, root, "WP1", ["file.txt"], [])
            replacement = json.loads(old_path.read_text(encoding="utf-8"))
            replacement["checkpoint_request_id"] = "WP1-replacement"
            replacement["supersedes"] = ["WP1"]
            replacement_path = old_path.with_name("WP1-replacement.json")
            replacement_path.write_text(json.dumps(replacement), encoding="utf-8")
            self.write_checkpoint_pointer(root, replacement_path)

            result = OPENCODE_CHECKPOINT.checkpoint(root)

            self.assertEqual(result["stage"], "WP1")
            self.assertEqual(json.loads(old_path.read_text(encoding="utf-8"))["state"], "READY")
            self.assertEqual(json.loads(replacement_path.read_text(encoding="utf-8"))["state"], "COMPLETED")

    @unittest.skipIf(os.name == "nt", "symlink behavior differs on Windows")
    def test_checkpoint_helper_rejects_symlinked_workflow_root(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as external_temporary:
            root = Path(temporary).resolve()
            external = Path(external_temporary).resolve()
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Checkpoint Test")
            self.git(root, "config", "user.email", "checkpoint@example.invalid")
            (root / ".gitignore").write_text("/.orchestrator/\n", encoding="utf-8")
            (root / "file.txt").write_text("before\n", encoding="utf-8")
            self.git(root, "add", ".gitignore", "file.txt")
            self.git(root, "commit", "-qm", "baseline")
            (root / "file.txt").write_text("after\n", encoding="utf-8")
            requests = external / "tasks" / "workflow" / "snapshots" / "checkpoint-requests"
            requests.mkdir(parents=True)
            (root / ".orchestrator").symlink_to(external, target_is_directory=True)
            request = {
                "schema": "orchestrator-checkpoint-v1",
                "checkpoint_request_id": "WP1",
                "supersedes": [],
                "state": "READY",
                "purpose": "STAGE",
                "workspace_root": str(root),
                "workflow_root": str(root / ".orchestrator" / "tasks" / "workflow"),
                "git_repository_root": str(root),
                "expected_head": self.git(root, "rev-parse", "HEAD", capture_output=True).stdout.strip(),
                "expected_branch_ref": self.git(root, "symbolic-ref", "-q", "HEAD", capture_output=True).stdout.strip(),
                "stage": "WP1",
                "declared_paths": ["file.txt"],
                "declared_path_states": {"file.txt": OPENCODE_CHECKPOINT.path_state(root, "file.txt")},
                "declared_git_states": {"file.txt": OPENCODE_CHECKPOINT.git_state(root, root, "file.txt")},
                "baseline_user_paths": [],
                "reviewed_index_digest": OPENCODE_CHECKPOINT.index_digest(OPENCODE_CHECKPOINT.index_entries(root), set()),
                "product_snapshot_id": "a" * 64,
                "review_epoch_id": "b" * 64,
                "plan_structure_id": "c" * 64,
                "subject": "checkpoint WP1",
            }
            request_path = requests / "WP1.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            self.write_checkpoint_pointer(root, request_path)

            with self.assertRaisesRegex(OPENCODE_CHECKPOINT.CheckpointError, "symlink component"):
                OPENCODE_CHECKPOINT.checkpoint(root)

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

    @staticmethod
    def git(root, *arguments, capture_output=False):
        return subprocess.run(["git", *arguments], cwd=root, check=True, text=True, capture_output=capture_output)

    def write_checkpoint_request(self, workspace, git_root, stage, declared_paths, baseline_user_paths):
        requests = workspace / ".orchestrator" / "tasks" / "workflow" / "snapshots" / "checkpoint-requests"
        requests.mkdir(parents=True, exist_ok=True)
        request = {
            "schema": "orchestrator-checkpoint-v1",
            "checkpoint_request_id": stage,
            "supersedes": [],
            "state": "READY",
            "purpose": "STAGE",
            "workspace_root": str(workspace),
            "workflow_root": str(workspace / ".orchestrator" / "tasks" / "workflow"),
            "git_repository_root": str(git_root),
            "expected_head": self.git(git_root, "rev-parse", "HEAD", capture_output=True).stdout.strip(),
            "expected_branch_ref": self.git(git_root, "symbolic-ref", "-q", "HEAD", capture_output=True).stdout.strip(),
            "stage": stage,
            "declared_paths": declared_paths,
            "declared_path_states": {path: OPENCODE_CHECKPOINT.path_state(workspace, path) for path in declared_paths},
            "declared_git_states": {path: OPENCODE_CHECKPOINT.git_state(workspace, git_root, path) for path in declared_paths},
            "baseline_user_paths": baseline_user_paths,
            "reviewed_index_digest": OPENCODE_CHECKPOINT.index_digest(OPENCODE_CHECKPOINT.index_entries(git_root), set()),
            "product_snapshot_id": "a" * 64,
            "review_epoch_id": "b" * 64,
            "plan_structure_id": "c" * 64,
            "subject": f"checkpoint {stage}",
        }
        path = requests / f"{stage}.json"
        path.write_text(json.dumps(request), encoding="utf-8")
        self.write_checkpoint_pointer(workspace, path)
        return path

    @staticmethod
    def write_checkpoint_pointer(workspace, request_path):
        workflow_root = request_path.parents[2]
        pointer = {
            "schema": "orchestrator-checkpoint-pointer-v1",
            "workflow_root": str(workflow_root),
            "request": str(request_path.relative_to(workflow_root)).replace(os.sep, "/"),
        }
        pointer_path = workspace / ".orchestrator" / "checkpoint-active.json"
        pointer_path.parent.mkdir(parents=True, exist_ok=True)
        pointer_path.write_text(json.dumps(pointer), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
