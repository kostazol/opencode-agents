import base64
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "opencode-agents.py"
AGENT_NAMES = [
    "orchestrator-analyst.md",
    "orchestrator-executor.md",
    "orchestrator-final-reviewer.md",
    "orchestrator-plan-reviewer.md",
    "orchestrator-recon.md",
    "orchestrator-task-adjuster.md",
    "orchestrator-task-executor.md",
    "orchestrator-task-planner.md",
    "orchestrator-task-reviewer.md",
]
TERRA_AGENTS = {
    "orchestrator-final-reviewer.md",
    "orchestrator-plan-reviewer.md",
    "orchestrator-task-adjuster.md",
    "orchestrator-task-planner.md",
}
SPEC = importlib.util.spec_from_file_location("opencode_agents", CLI)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load opencode-agents.py")
OPENCODE_AGENTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPENCODE_AGENTS)


class CliTests(unittest.TestCase):
    def run_cli(self, source, target, command, *arguments, capture_output=False):
        return subprocess.run([sys.executable, str(CLI), "--source", str(source), "--target", str(target), command, *arguments], check=True, capture_output=capture_output, text=True)

    def installed_agents(self, target):
        return {path.name: path.read_text(encoding="utf-8") for path in sorted((target / "agents").glob("*.md"))}

    def permission_rules(self, content, permission):
        lines = content.splitlines()
        scalar = re.compile(rf"  {re.escape(permission)}: (allow|ask|deny)")
        for index, line in enumerate(lines):
            match = scalar.fullmatch(line)
            if match:
                return [("*", match.group(1))]
            if line != f"  {permission}:":
                continue
            rules = []
            rule = re.compile(r'''    ("(?:\\.|[^"\\])*"|'(?:''|[^'])*'|[^\s:]+): (allow|ask|deny)''')
            for candidate in lines[index + 1:]:
                if not candidate.startswith("    "):
                    break
                match = rule.fullmatch(candidate)
                if match:
                    key = match.group(1)
                    pattern = json.loads(key) if key.startswith('"') else key[1:-1].replace("''", "'") if key.startswith("'") else key
                    rules.append((pattern, match.group(2)))
            return rules
        raise AssertionError(f"permission not found: {permission}")

    def evaluate(self, rules, value):
        result = "ask"
        for pattern, action in rules:
            expression = "".join(".*" if character == "*" else "." if character == "?" else re.escape(character) for character in pattern)
            if re.fullmatch(expression, value, flags=re.DOTALL):
                result = action
        return result

    def test_permission_evaluator_decodes_escapes_and_uses_last_match(self):
        content = 'permission:\n  bash:\n    "*": allow\n    "*\\n*": deny\n    "*\\r*": deny\n    \'safe\': allow\n'
        rules = self.permission_rules(content, "bash")
        self.assertEqual(self.evaluate(rules, "unsafe\ncommand"), "deny")
        self.assertEqual(self.evaluate(rules, "unsafe\rcommand"), "deny")
        self.assertEqual(self.evaluate(rules, "safe"), "allow")

    def test_fresh_install_has_self_contained_agents(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(ROOT, target, "install")
            agents = self.installed_agents(target)
            self.assertEqual(sorted(agents), AGENT_NAMES)
            self.assertEqual([name for name, content in agents.items() if re.search(r"^mode: primary$", content, re.MULTILINE)], ["orchestrator-analyst.md", "orchestrator-executor.md"])
            for content in agents.values():
                self.assertNotRegex(content, r"__[A-Z][A-Z0-9_]+__")
                self.assertIn("# OpenCode Agents version: 1.0.0", content)
                self.assertNotIn("protocols/orchestrator.md", content)
                self.assertNotIn("Read `__OPENCODE", content)
            self.assertFalse((target / "protocols").exists())
            self.assertFalse((target / "helpers").exists())

    def test_models_match_two_primary_architecture(self):
        source_agents = self.installed_agents(ROOT)
        pinned = {name for name, content in source_agents.items() if re.search(r"^model:", content, re.MULTILINE)}
        self.assertEqual(pinned, TERRA_AGENTS)
        for name in TERRA_AGENTS:
            self.assertIsNotNone(re.search(r"^model: openai/gpt-5\.6-terra$", source_agents[name], re.MULTILINE))
        for name in ("orchestrator-task-executor.md", "orchestrator-task-reviewer.md"):
            self.assertIsNone(re.search(r"^model:", source_agents[name], re.MULTILINE))
            self.assertIn("Model inherits caller selection", source_agents[name])

    def test_agent_local_contracts_are_complete(self):
        planner = (ROOT / "agents/orchestrator-task-planner.md").read_text(encoding="utf-8")
        sections = ("## Goal", "## Acceptance criteria", "## Ordered prerequisites", "## Branch preconditions", "## Repository context", "## Scope", "## Implementation", "## Test work", "## Validation", "## Approved scope amendments", "## Current repair direction", "## Execution record")
        for section in sections:
            self.assertIn(section, planner)
        executor = (ROOT / "agents/orchestrator-executor.md").read_text(encoding="utf-8")
        adjuster = (ROOT / "agents/orchestrator-task-adjuster.md").read_text(encoding="utf-8")
        for field in ("Finding:", "Source:", "Cycle:", "Ordinary repair attempt:", "Status:", "Evidence:", "Requirement:", "Scope impact:", "Supersedes:"):
            self.assertIn(field, executor)
            self.assertIn(field, adjuster)
        self.assertIn("Do not expose or quote journals", executor)
        self.assertIn("Do not expose or quote journals", (ROOT / "agents/orchestrator-analyst.md").read_text(encoding="utf-8"))

    def test_primary_task_allowlists_are_exact(self):
        agents = self.installed_agents(ROOT)
        expected = {
            "orchestrator-analyst.md": {"orchestrator-recon", "orchestrator-task-planner", "orchestrator-plan-reviewer"},
            "orchestrator-executor.md": {"orchestrator-task-executor", "orchestrator-task-reviewer", "orchestrator-task-adjuster", "orchestrator-final-reviewer"},
        }
        for name, allowlist in expected.items():
            rules = self.permission_rules(agents[name], "task")
            self.assertEqual({pattern for pattern, action in rules if action == "allow"}, allowlist)
            self.assertEqual(self.evaluate(rules, "general"), "deny")

    def test_write_boundaries_and_read_only_reviewers(self):
        agents = self.installed_agents(ROOT)
        for name in ("orchestrator-task-planner.md", "orchestrator-task-adjuster.md"):
            rules = self.permission_rules(agents[name], "edit")
            self.assertEqual(self.evaluate(rules, ".orchestrator/request/tasks/01-task.md"), "allow")
            self.assertEqual(self.evaluate(rules, "src/Program.cs"), "deny")
            self.assertEqual(self.evaluate(rules, ".git/config"), "deny")
        planner_edits = self.permission_rules(agents["orchestrator-task-planner.md"], "edit")
        self.assertEqual(self.evaluate(planner_edits, ".orchestrator/request/tasks/01-task.issues.md"), "deny")
        self.assertEqual(self.evaluate(planner_edits, ".orchestrator/nested/request/tasks/01-task.md"), "deny")
        self.assertEqual(self.evaluate(planner_edits, ".orchestrator/request/tasks/nested/01-task.md"), "deny")
        self.assertIn("Edit only supplied task and sibling", agents["orchestrator-task-adjuster.md"])
        for name in ("orchestrator-plan-reviewer.md", "orchestrator-task-reviewer.md", "orchestrator-final-reviewer.md"):
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "edit"), ".orchestrator/request/tasks/01-task.md"), "deny")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "edit"), "src/Program.cs"), "deny")
        executor_edits = self.permission_rules(agents["orchestrator-task-executor.md"], "edit")
        self.assertEqual(self.evaluate(executor_edits, "src/Program.cs"), "allow")
        self.assertEqual(self.evaluate(executor_edits, ".git"), "deny")
        self.assertEqual(self.evaluate(executor_edits, ".git/index"), "deny")
        self.assertEqual(self.evaluate(executor_edits, "repo/.git/config"), "deny")
        self.assertEqual(self.evaluate(executor_edits, ".orchestrator/request/tasks/01-task.md"), "deny")

    def test_secret_reads_are_denied(self):
        agents = self.installed_agents(ROOT)
        for name, content in agents.items():
            rules = self.permission_rules(content, "read")
            for path in ("private.pem", "identity.key", ".npmrc", ".netrc", "id_rsa", "id_ed25519"):
                self.assertEqual(self.evaluate(rules, path), "deny", f"{name}: {path}")
            self.assertEqual(self.evaluate(rules, "/tmp/secrets-config/nested/file.txt"), "deny", name)
        for name in ("orchestrator-task-executor.md", "orchestrator-task-reviewer.md", "orchestrator-task-adjuster.md", "orchestrator-final-reviewer.md"):
            rules = self.permission_rules(agents[name], "read")
            for path in (".env", "prod.env", "settings.env.local", ".npmrc", ".netrc", "service-credentials.json"):
                self.assertEqual(self.evaluate(rules, path), "deny", f"{name}: {path}")

    def test_command_permissions_allow_safe_work_and_deny_unsafe_shell(self):
        agents = self.installed_agents(ROOT)
        command_agents = ("orchestrator-executor.md", "orchestrator-task-executor.md", "orchestrator-task-reviewer.md", "orchestrator-task-adjuster.md", "orchestrator-final-reviewer.md")
        mutation_commands = ("git add .", "git commit -m unsafe", "git reset --hard", "git checkout main", "git switch main", "git clean -fd", "git stash", "git merge topic", "git rebase main", "git push")
        for name in command_agents:
            rules = self.permission_rules(agents[name], "bash")
            self.assertEqual(self.evaluate(rules, "git diff --no-ext-diff --no-textconv --name-only --"), "allow", name)
            self.assertEqual(self.evaluate(rules, "git diff --no-ext-diff --no-textconv --check --"), "allow", name)
            for command in mutation_commands:
                self.assertEqual(self.evaluate(rules, command), "deny", f"{name}: {command}")
            for command in ("git diff --no-ext-diff --no-textconv -- src/app.py; git add .", "git diff --no-ext-diff --no-textconv -- src/app.py && git commit -m unsafe", "git diff --no-ext-diff --no-textconv -- src/app.py\ngit add .", "git diff --no-ext-diff --no-textconv -- src/app.py\rgit add ."):
                self.assertEqual(self.evaluate(rules, command), "deny", f"{name}: separator")
        for name in ("orchestrator-task-executor.md", "orchestrator-task-reviewer.md", "orchestrator-final-reviewer.md"):
            rules = self.permission_rules(agents[name], "bash")
            for command in ("dotnet test Tests.csproj", "npm test", "pytest tests", "cargo test"):
                self.assertEqual(self.evaluate(rules, command), "allow", f"{name}: {command}")
            for command in ("dotnet run --no-build", "python3 tests/test-cli.py", "bash tests/test-cli.sh", "python3 -m py_compile opencode-agents.py", "opencode debug config"):
                self.assertEqual(self.evaluate(rules, command), "allow", f"{name}: {command}")
            self.assertEqual(self.evaluate(rules, "curl http://localhost:8080/health"), "deny")
            self.assertEqual(self.evaluate(rules, "curl https://example.com/api"), "deny")
            for command in ("npm test -- ftp://example.com", "pytest tests/../../tmp/unsafe.py", "dotnet test -o /tmp/output", "dotnet test --output=/tmp/output", "npm test -- --prefix=/tmp/output", "pytest ~/outside.py", "python3 opencode-agents.py --target /tmp/out install"):
                self.assertEqual(self.evaluate(rules, command), "deny", f"{name}: {command}")

    def test_update_preserves_unknown_agents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            self.run_cli(ROOT, target, "install")
            unknown = target / "agents/user-agent.md"
            unknown.write_text("user\n", encoding="utf-8")
            self.run_cli(ROOT, target, "update", "--backup-dir", str(backup))
            self.assertEqual(unknown.read_text(encoding="utf-8"), "user\n")
            self.assertFalse(backup.exists())

    def test_status_and_global_caveman_guidance(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(ROOT, target, "install")
            result = self.run_cli(ROOT, target, "status", capture_output=True)
            self.assertIn("summary missing=0 changed=0 current=10", result.stdout)
            instructions = (target / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(instructions.count(OPENCODE_AGENTS.GLOBAL_INSTRUCTIONS_START), 1)
            self.assertIn("caveman", instructions)

    def test_complete_github_api_source_installs_agents_only(self):
        files = [ROOT / "AGENTS.md", *sorted((ROOT / "agents").glob("*.md"))]
        tree = {"tree": []}
        blobs = {}
        for index, path in enumerate(files):
            relative = path.relative_to(ROOT).as_posix()
            sha = f"blob-{index}"
            tree["tree"].append({"path": relative, "type": "blob", "sha": sha})
            blobs[sha] = path.read_bytes()

        def github_response(url, token):
            if "/git/trees/" in url:
                return tree
            sha = url.rsplit("/", 1)[1]
            return {"content": base64.b64encode(blobs[sha]).decode()}

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            arguments = [str(CLI), "install", "--repository", "kostazol/opencode-agents", "--ref", "main", "--target", str(target)]
            with patch.object(OPENCODE_AGENTS, "github_json", side_effect=github_response), patch.object(sys, "argv", arguments):
                self.assertEqual(OPENCODE_AGENTS.main(), 0)
            self.assertEqual(sorted(self.installed_agents(target)), AGENT_NAMES)
            self.assertFalse((target / "protocols").exists())
            self.assertFalse((target / "helpers").exists())

    def test_repository_urls_and_invalid_github_json(self):
        self.assertEqual(OPENCODE_AGENTS.repository_name("kostazol/opencode-agents"), "kostazol/opencode-agents")
        self.assertEqual(OPENCODE_AGENTS.repository_name("https://github.com/kostazol/opencode-agents.git"), "kostazol/opencode-agents")
        for url in ("http://github.com/kostazol/opencode-agents", "https://example.com/kostazol/opencode-agents", "https://github.com/kostazol"):
            with self.assertRaises(RuntimeError):
                OPENCODE_AGENTS.repository_name(url)
        with self.assertRaisesRegex(RuntimeError, "GitHub API URL must use HTTPS"):
            OPENCODE_AGENTS.github_json("http://api.github.com/repos/kostazol/opencode-agents", None)
        with self.assertRaisesRegex(RuntimeError, "GITHUB_TOKEN may only be sent"):
            OPENCODE_AGENTS.github_json("https://api.github.test/repos/kostazol/opencode-agents", "secret")
        response = MagicMock()
        response.read.return_value = b"{"
        context = MagicMock()
        context.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = context
        with patch.object(OPENCODE_AGENTS, "build_opener", return_value=opener):
            with self.assertRaisesRegex(RuntimeError, "GitHub API returned invalid JSON"):
                OPENCODE_AGENTS.github_json("https://api.github.com/repos/kostazol/opencode-agents", None)

    @unittest.skipIf(sys.platform == "win32", "symlink behavior differs on Windows")
    def test_symlink_target_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actual = root / "actual"
            actual.mkdir()
            target = root / "config"
            target.symlink_to(actual, target_is_directory=True)
            result = subprocess.run([sys.executable, str(CLI), "--source", str(ROOT), "--target", str(target), "install"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing symlink target path", result.stderr)
            self.assertEqual(list(actual.iterdir()), [])

if __name__ == "__main__":
    unittest.main()
