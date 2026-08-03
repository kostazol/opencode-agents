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
    "orchestrator-analyst-single-model.md",
    "orchestrator-analyst.md",
    "orchestrator-executor-single-model.md",
    "orchestrator-executor.md",
    "orchestrator-final-reviewer.md",
    "orchestrator-plan-reviewer.md",
    "orchestrator-plan-ultra-reviewer.md",
    "orchestrator-stage-decomposer.md",
    "orchestrator-stage-pair-reviewer.md",
    "orchestrator-stage-question-reviewer.md",
    "orchestrator-task-adjuster.md",
    "orchestrator-task-executor.md",
    "orchestrator-task-planner.md",
    "orchestrator-task-reviewer-single-model.md",
    "orchestrator-task-reviewer.md",
]
PLUGIN_NAMES = ["analyst-workflow-guard.js"]
PINNED_AGENTS = {
    "orchestrator-final-reviewer.md": "openai/gpt-5.6-terra",
    "orchestrator-plan-ultra-reviewer.md": "openai/gpt-5.6-sol",
    "orchestrator-task-adjuster.md": "openai/gpt-5.6-terra",
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

    def installed_plugins(self, target):
        return {path.name: path.read_text(encoding="utf-8") for path in sorted((target / "plugins").glob("*.js"))}

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
            plugins = self.installed_plugins(target)
            self.assertEqual(sorted(agents), AGENT_NAMES)
            self.assertEqual(sorted(plugins), PLUGIN_NAMES)
            self.assertEqual([name for name, content in agents.items() if re.search(r"^mode: primary$", content, re.MULTILINE)], ["orchestrator-analyst-single-model.md", "orchestrator-analyst.md", "orchestrator-executor-single-model.md", "orchestrator-executor.md"])
            version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
            self.assertEqual(version, "3.0.0")
            self.assertEqual(OPENCODE_AGENTS.VERSION, version)
            for content in agents.values():
                self.assertNotRegex(content, r"__[A-Z][A-Z0-9_]+__")
                self.assertIn(f"# OpenCode Agents version: {version}", content)
                self.assertNotIn("protocols/orchestrator.md", content)
                self.assertNotIn("Read `__OPENCODE", content)
            self.assertIn(f'const VERSION = "{version}"', plugins["analyst-workflow-guard.js"])
            self.assertFalse((target / "protocols").exists())
            self.assertFalse((target / "helpers").exists())

    def test_breaking_workflow_rename_documentation(self):
        maintenance = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        hidden_workflow = "." + "orchestrator"
        current_contracts = [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "opencode-agents.py", *sorted((ROOT / "agents").glob("*.md"))]
        for path in current_contracts:
            self.assertNotIn(hidden_workflow, path.read_text(encoding="utf-8"), path.name)
        self.assertIn("1_orchestrator/<request>/tasks/", maintenance)
        self.assertIn("`1_orchestrator` всегда находится внутри working directory текущей OpenCode session", readme)
        self.assertIn("## 2.0.0 - 2026-08-02", changelog)
        self.assertIn("Rename workflow artifact directory", changelog)
        self.assertIn("Support only `1_orchestrator` workflow artifacts; no compatibility or migration path is provided", changelog)
        self.assertIn("## 2.2.0 - 2026-08-02", changelog)
        self.assertIn("Batch every independent actionable plan-review finding", changelog)
        self.assertIn("## 2.2.1 - 2026-08-02", changelog)
        self.assertIn("Normalize semantically complete singular, unnumbered, and imperfectly numbered", changelog)
        self.assertIn("## 2.3.1 - 2026-08-02", changelog)
        self.assertIn("absent from OpenCode's status map as idle", changelog)
        self.assertIn("## 3.0.0 - 2026-08-02", changelog)
        self.assertIn("replace monolithic analyst planning with fresh decomposition", changelog)
        self.assertIn("schema-validated `workflow_certificate` tool calls", changelog)

    def test_models_match_standard_and_single_model_architecture(self):
        source_agents = self.installed_agents(ROOT)
        pinned = {name for name, content in source_agents.items() if re.search(r"^model:", content, re.MULTILINE)}
        self.assertEqual(pinned, set(PINNED_AGENTS))
        for name, model in PINNED_AGENTS.items():
            self.assertIsNotNone(re.search(rf"^model: {re.escape(model)}$", source_agents[name], re.MULTILINE))
        for name in ("orchestrator-plan-reviewer.md", "orchestrator-stage-decomposer.md", "orchestrator-stage-pair-reviewer.md", "orchestrator-stage-question-reviewer.md", "orchestrator-task-executor.md", "orchestrator-task-planner.md", "orchestrator-task-reviewer-single-model.md", "orchestrator-task-reviewer.md"):
            self.assertIsNone(re.search(r"^model:", source_agents[name], re.MULTILINE))
            self.assertIn("Model inherits caller selection", source_agents[name])

    def test_staged_analyst_role_contracts_are_complete(self):
        decomposer = (ROOT / "agents/orchestrator-stage-decomposer.md").read_text(encoding="utf-8")
        question_reviewer = (ROOT / "agents/orchestrator-stage-question-reviewer.md").read_text(encoding="utf-8")
        planner = (ROOT / "agents/orchestrator-task-planner.md").read_text(encoding="utf-8")
        stage_reviewer = (ROOT / "agents/orchestrator-plan-reviewer.md").read_text(encoding="utf-8")
        pair_reviewer = (ROOT / "agents/orchestrator-stage-pair-reviewer.md").read_text(encoding="utf-8")
        ultra = (ROOT / "agents/orchestrator-plan-ultra-reviewer.md").read_text(encoding="utf-8")
        sections = ("## Goal", "## Acceptance criteria", "## Ordered prerequisites", "## Branch preconditions", "## Repository context", "## Scope", "## Implementation", "## Test work", "## Validation", "## Approved scope amendments", "## Current repair direction", "## Execution record")
        for section in sections:
            self.assertIn(section, planner)
        for field in ("Stage ID:", "Stage title:", "Stage sequence:", "Stage revision:", "Approval ID:", "Status: DRAFT", "Planning review: PENDING"):
            self.assertIn(field, planner)
        for name in ("orchestrator-stage-decomposer.md", "orchestrator-stage-question-reviewer.md", "orchestrator-task-planner.md", "orchestrator-plan-reviewer.md", "orchestrator-stage-pair-reviewer.md", "orchestrator-plan-ultra-reviewer.md"):
            content = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("This prompt is self-contained: do not read OpenCode configuration, agent prompts, or runtime protocol files.", content, name)
        self.assertIn("`INITIAL` proposes stages for independent question review", decomposer)
        self.assertIn("`RESTAGE` always starts fresh after question review, whether questions existed or not", decomposer)
        self.assertIn("Re-read repository evidence independently; do not merely confirm INITIAL", decomposer)
        self.assertIn("No role may write tasks from INITIAL output", decomposer)
        self.assertIn("one exhaustive batch", question_reviewer)
        self.assertIn("repository evidence and safe reversible defaults cannot resolve", question_reviewer)
        self.assertIn("without follow-up", question_reviewer)
        self.assertIn("Plan only supplied current stage", planner)
        self.assertIn("Do not create, edit, rename, supersede, or delete tasks belonging to another stage", planner)
        self.assertIn("Fresh independent review of exactly one current planning stage", stage_reviewer)
        self.assertIn("Review whole stage before verdict", stage_reviewer)
        self.assertIn("after all stages are individually planned and reviewed", pair_reviewer)
        self.assertIn("exactly one adjacent certified stage pair", pair_reviewer)
        self.assertIn("`S01+S02`, `S02+S03`, and so on", ultra)
        self.assertEqual(self.evaluate(self.permission_rules(ultra, "grep"), "src/Program.cs"), "deny")

    def test_primary_staged_workflow_order_and_backtracking(self):
        analyst = (ROOT / "agents/orchestrator-analyst.md").read_text(encoding="utf-8")
        single_analyst = (ROOT / "agents/orchestrator-analyst-single-model.md").read_text(encoding="utf-8")
        for content in (analyst, single_analyst):
            workflow = content[content.index("<workflow priority="):content.index("</workflow>")]
            initial = workflow.index("Dispatch fresh decomposer `INITIAL`")
            questions = workflow.index("Dispatch fresh question reviewer with exact INITIAL output")
            restage = workflow.index("fresh decomposer `RESTAGE`", questions)
            approval = workflow.index("Require exact `APPROVE <approval-id>`")
            self.assertLess(initial, questions)
            self.assertLess(questions, restage)
            self.assertLess(restage, approval)
            if content is analyst:
                self.assertIn("No task or journal write before exact approval", content)
                self.assertIn("For each stage S01 through SNN sequentially", content)
            else:
                self.assertIn("No planner dispatch, task, or journal write before approval", content)
                self.assertIn("Sequentially for S01 through SNN", content)
            self.assertIn("fresh stage reviewer", content)
            self.assertIn("`REVISE_STAGE`", content)
            self.assertIn("until PASS", content)
            self.assertIn("After all stages", content)
            self.assertIn("S01+S02", content)
            self.assertIn("S02+S03", content)
            self.assertLess(content.index("After all stages"), content.index("S01+S02"))
            for invariant in ("behavior", "boundaries", "dependencies", "expected paths", "contracts", "test ownership/cases", "execution ordering", "approvals", "non-goals"):
                self.assertIn(invariant, content)
        self.assertIn("fresh Sol ultra in `BACKTRACK_AUTHORITY`", analyst)
        self.assertIn("After all current stage and pair PASS responses, dispatch fresh Sol ultra `FINAL`", analyst)
        self.assertIn("Only clean FINAL PASS proceeds", analyst)
        self.assertNotIn("orchestrator-plan-ultra-reviewer", single_analyst)
        self.assertIn("`RESTART <lineage-id> FROM <stage-id>`", single_analyst)
        self.assertIn("`KEEP <lineage-id>`", single_analyst)
        self.assertIn("Do not choose for user", single_analyst)

    def test_executor_and_workflow_base_contracts_are_preserved(self):
        executor = (ROOT / "agents/orchestrator-executor.md").read_text(encoding="utf-8")
        adjuster = (ROOT / "agents/orchestrator-task-adjuster.md").read_text(encoding="utf-8")
        for field in ("Finding:", "Source:", "Cycle:", "Ordinary repair attempt:", "Status:", "Evidence:", "Requirement:", "Scope impact:", "Supersedes:"):
            self.assertIn(field, executor)
            self.assertIn(field, adjuster)
        self.assertIn("Do not expose or quote journals", executor)
        single_executor = (ROOT / "agents/orchestrator-executor-single-model.md").read_text(encoding="utf-8")
        self.assertNotIn("orchestrator-final-reviewer", single_executor)
        self.assertNotIn("orchestrator-task-adjuster", single_executor)
        self.assertIn("Only reviewer `MODE: REVIEW` with `SINGLE_REVIEW: PASS` completes this workflow", single_executor)
        self.assertIn("read full sibling journal only to count matching semantic-signature entries", single_executor)
        single_reviewer = (ROOT / "agents/orchestrator-task-reviewer-single-model.md").read_text(encoding="utf-8")
        self.assertIn("SINGLE_REVIEW: PASS|FINDING_ADJUSTED|BLOCKED", single_reviewer)
        self.assertIn("SINGLE_REVIEW: FINDING_ADJUSTED|BLOCKED", single_reviewer)
        self.assertNotIn("SINGLE_REVIEW: PASS|FINDING_ADJUSTED|BLOCKED\nMODE: ADJUST_EXECUTOR_FINDING", single_reviewer)
        self.assertIn("update only task `Current repair direction`", single_reviewer)
        self.assertIn("Only workflow-designated task-correction authority can expand scope", (ROOT / "agents/orchestrator-task-executor.md").read_text(encoding="utf-8"))
        workflow_base_agents = tuple(AGENT_NAMES)
        for name in workflow_base_agents:
            content = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("WORKFLOW_BASE", content, name)
        for name in ("orchestrator-analyst.md", "orchestrator-analyst-single-model.md"):
            content = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("Capture OpenCode session working directory as immutable `WORKFLOW_BASE`", content)
            self.assertIn("never derive it from Git root, repository root, parent directory, or subagent working directory", content)
            self.assertIn("deterministic", content)
            self.assertIn("target", content)
        for name in ("orchestrator-executor.md", "orchestrator-executor-single-model.md"):
            content = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("Git root is separate and may be used only for Git-state inspection", content)
            self.assertIn("Reject Git-root or parent `1_orchestrator` when it differs from `WORKFLOW_BASE`", content)
            self.assertIn("Compute immutable `WORKFLOW_GIT_PREFIX`", content)
            self.assertIn("Compute immutable `WORKFLOW_PRODUCT_GIT_PREFIX`", content)
            self.assertIn("empty when roots match", content)
            self.assertIn("WORKFLOW_PRODUCT_GIT_PREFIX + 1_orchestrator/", content)
            self.assertIn("Classify only Git status paths under exact `WORKFLOW_GIT_PREFIX` as workflow-owned", content)
            self.assertIn("Pass immutable `WORKFLOW_BASE`, `WORKFLOW_PRODUCT_GIT_PREFIX`, and `WORKFLOW_GIT_PREFIX` explicitly to every subagent", content)
            self.assertIn("strip that prefix before comparing with `WORKFLOW_BASE`-relative expected product paths", content)
            self.assertIn("Git root `/repo` and base `/repo/src/App` produce product prefix `src/App/`", content)
            self.assertIn("Git path `src/App/lib/a.cs` normalizes to `lib/a.cs`", content)
            self.assertIn("Git-root `1_orchestrator/` is outside workflow scope", content)
            self.assertGreaterEqual(content.count("all three immutable workflow values"), 3, name)
        git_prefix_consumers = ("orchestrator-task-executor.md", "orchestrator-task-reviewer.md", "orchestrator-task-reviewer-single-model.md", "orchestrator-task-adjuster.md", "orchestrator-final-reviewer.md")
        for name in git_prefix_consumers:
            content = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("WORKFLOW_GIT_PREFIX", content, name)
            self.assertIn("WORKFLOW_PRODUCT_GIT_PREFIX", content, name)
            self.assertIn("Git-root substitution only when root differs from `WORKFLOW_BASE`", content, name)
        for name in ("orchestrator-task-reviewer.md", "orchestrator-task-reviewer-single-model.md", "orchestrator-final-reviewer.md"):
            content = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("excluding only Git paths under exact `WORKFLOW_GIT_PREFIX`", content, name)
            self.assertIn("outside-prefix path", content, name)

    def test_reassessment_contracts_are_preserved(self):
        planner = (ROOT / "agents/orchestrator-task-planner.md").read_text(encoding="utf-8")
        for name in ("orchestrator-analyst.md", "orchestrator-analyst-single-model.md"):
            analyst = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("Select `REASSESS` only when user explicitly supplies one existing", analyst, name)
            self.assertNotIn("SATISFIED", analyst, name)
        for contract in (
            "completed tasks with `Status: COMPLETE`, `Planning review: PASS`, and execution `Result: PASS` are immutable",
            "If any task is `IN_PROGRESS` or `BLOCKED`, return `BLOCKED` before edits",
            "A completed-outcome gap gets a new corrective task",
            "Obsolete unexecuted tasks may be marked `SUPERSEDED` only while editing their own stage",
            "Never renumber or delete task files",
            "next unused two-digit number through `99`",
        ):
            self.assertIn(contract, planner)
        for name in ("orchestrator-executor.md", "orchestrator-executor-single-model.md"):
            executor = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("Reject `DRAFT`, `SUPERSEDED`, and `COMPLETE`", executor)

    def test_structured_certificate_and_guard_contracts(self):
        agents = self.installed_agents(ROOT)
        analysts = {"orchestrator-analyst.md", "orchestrator-analyst-single-model.md"}
        for name, content in agents.items():
            if name in analysts:
                self.assertEqual(self.evaluate(self.permission_rules(content, "workflow_certificate"), "*"), "allow")
            else:
                self.assertNotRegex(content, r"^  workflow_certificate: allow$", name)
        fields = ("protocolVersion", "workflow", "lineageID", "state", "phase", "target", "approvalID", "stageID", "stageRevision", "pairID", "generation", "nextAction", "summary")
        states = "RUNNING|WAITING_ANSWERS|WAITING_APPROVAL|BLOCKED|COMPLETE"
        for name in analysts:
            content = agents[name]
            self.assertIn('`protocolVersion: "3"`', content)
            self.assertIn(states, content)
            for field in fields:
                self.assertIn(field, content)
        plugin = (ROOT / "plugins/analyst-workflow-guard.js").read_text(encoding="utf-8")
        self.assertIn('tool: { workflow_certificate: workflowCertificate }', plugin)
        self.assertIn('part.tool !== "workflow_certificate"', plugin)
        self.assertIn('part.state?.status !== "completed"', plugin)
        self.assertIn('Use structured workflow certificates only. Do not parse prior prose', plugin)
        self.assertNotIn("PLANNING: PASS", plugin)
        self.assertNotIn("Итог:", plugin)
        self.assertIn('event.type === "session.status"', plugin)
        self.assertIn('if (decision.variant !== undefined) body.variant = decision.variant', plugin)
        self.assertIn('continuationMessageID(sessionID, decision)', plugin)
        self.assertIn('decision.epochID, decision.triggerAssistantID, decision.frontier', plugin)

    def test_primary_task_allowlists_are_exact(self):
        agents = self.installed_agents(ROOT)
        expected = {
            "orchestrator-analyst-single-model.md": {"orchestrator-stage-decomposer", "orchestrator-stage-question-reviewer", "orchestrator-task-planner", "orchestrator-plan-reviewer", "orchestrator-stage-pair-reviewer"},
            "orchestrator-analyst.md": {"orchestrator-stage-decomposer", "orchestrator-stage-question-reviewer", "orchestrator-task-planner", "orchestrator-plan-reviewer", "orchestrator-stage-pair-reviewer", "orchestrator-plan-ultra-reviewer"},
            "orchestrator-executor-single-model.md": {"orchestrator-task-executor", "orchestrator-task-reviewer-single-model"},
            "orchestrator-executor.md": {"orchestrator-task-executor", "orchestrator-task-reviewer", "orchestrator-task-adjuster", "orchestrator-final-reviewer"},
        }
        for name, allowlist in expected.items():
            rules = self.permission_rules(agents[name], "task")
            self.assertEqual({pattern for pattern, action in rules if action == "allow"}, allowlist)
            self.assertEqual(self.evaluate(rules, "general"), "deny")

    def test_write_boundaries_and_read_only_reviewers(self):
        agents = self.installed_agents(ROOT)
        for name in ("orchestrator-task-planner.md", "orchestrator-task-adjuster.md", "orchestrator-task-reviewer-single-model.md"):
            rules = self.permission_rules(agents[name], "edit")
            self.assertEqual(self.evaluate(rules, "1_orchestrator/request/tasks/01-task.md"), "allow")
            self.assertEqual(self.evaluate(rules, "src/Program.cs"), "deny")
            self.assertEqual(self.evaluate(rules, ".git/config"), "deny")
        planner_edits = self.permission_rules(agents["orchestrator-task-planner.md"], "edit")
        self.assertEqual(self.evaluate(planner_edits, "1_orchestrator/request/planning-issues.md"), "allow")
        self.assertEqual(self.evaluate(planner_edits, "1_orchestrator/request/tasks/01-task.issues.md"), "deny")
        self.assertEqual(self.evaluate(planner_edits, "1_orchestrator/nested/request/tasks/01-task.md"), "deny")
        self.assertEqual(self.evaluate(planner_edits, "1_orchestrator/request/tasks/nested/01-task.md"), "deny")
        self.assertEqual(self.evaluate(planner_edits, "../1_orchestrator/request/tasks/01-task.md"), "deny")
        self.assertIn("Edit only supplied task and sibling", agents["orchestrator-task-adjuster.md"])
        for name in ("orchestrator-stage-decomposer.md", "orchestrator-stage-question-reviewer.md", "orchestrator-plan-reviewer.md", "orchestrator-stage-pair-reviewer.md", "orchestrator-plan-ultra-reviewer.md", "orchestrator-task-reviewer.md", "orchestrator-final-reviewer.md"):
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "edit"), "1_orchestrator/request/tasks/01-task.md"), "deny")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "edit"), "src/Program.cs"), "deny")
        for name in ("orchestrator-analyst.md", "orchestrator-analyst-single-model.md"):
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "edit"), "1_orchestrator/request/tasks/01-task.md"), "deny")
        executor_edits = self.permission_rules(agents["orchestrator-task-executor.md"], "edit")
        self.assertEqual(self.evaluate(executor_edits, "src/Program.cs"), "allow")
        self.assertEqual(self.evaluate(executor_edits, ".git"), "deny")
        self.assertEqual(self.evaluate(executor_edits, ".git/index"), "deny")
        self.assertEqual(self.evaluate(executor_edits, "repo/.git/config"), "deny")
        self.assertEqual(self.evaluate(executor_edits, "1_orchestrator/request/tasks/01-task.md"), "deny")
        for name in ("orchestrator-executor.md", "orchestrator-executor-single-model.md"):
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "read"), "1_orchestrator/request/tasks/01-task.md"), "allow")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "glob"), "1_orchestrator/request/tasks/*.md"), "allow")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "edit"), "1_orchestrator/request/tasks/01-task.md"), "allow")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "read"), "../1_orchestrator/request/tasks/01-task.md"), "deny")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "glob"), "../1_orchestrator/request/tasks/*.md"), "deny")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "edit"), "../1_orchestrator/request/tasks/01-task.md"), "deny")
        for name in ("orchestrator-analyst.md", "orchestrator-analyst-single-model.md"):
            read_rules = self.permission_rules(agents[name], "read")
            self.assertFalse(any(action == "allow" for _, action in read_rules))
            self.assertEqual(self.evaluate(read_rules, "1_orchestrator"), "deny")
            self.assertEqual(self.evaluate(read_rules, "repo/1_orchestrator"), "deny")
            self.assertEqual(self.evaluate(read_rules, "1_orchestrator/request"), "deny")
            self.assertEqual(self.evaluate(read_rules, "1_orchestrator/request/tasks/01-task.md"), "deny")
            self.assertEqual(self.evaluate(read_rules, "../1_orchestrator"), "deny")
            self.assertEqual(self.evaluate(read_rules, "repo/../1_orchestrator"), "deny")
            self.assertEqual(self.evaluate(read_rules, "secrets/1_orchestrator"), "deny")
            self.assertEqual(self.evaluate(read_rules, "credentials/1_orchestrator"), "deny")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "glob"), "1_orchestrator/request/tasks/*.md"), "allow")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "glob"), "../1_orchestrator/request/tasks/*.md"), "deny")

    def test_secret_reads_are_denied(self):
        agents = self.installed_agents(ROOT)
        for name, content in agents.items():
            rules = self.permission_rules(content, "read")
            for path in ("private.pem", "identity.key", ".npmrc", ".netrc", "id_rsa", "id_ed25519"):
                self.assertEqual(self.evaluate(rules, path), "deny", f"{name}: {path}")
            self.assertEqual(self.evaluate(rules, "/tmp/secrets-config/nested/file.txt"), "deny", name)
        for name in ("orchestrator-task-executor.md", "orchestrator-task-reviewer.md", "orchestrator-task-reviewer-single-model.md", "orchestrator-task-adjuster.md", "orchestrator-final-reviewer.md"):
            rules = self.permission_rules(agents[name], "read")
            for path in (".env", "prod.env", "settings.env.local", ".npmrc", ".netrc", "service-credentials.json"):
                self.assertEqual(self.evaluate(rules, path), "deny", f"{name}: {path}")

    def test_command_permissions_allow_safe_work_and_deny_unsafe_shell(self):
        agents = self.installed_agents(ROOT)
        command_agents = ("orchestrator-executor.md", "orchestrator-executor-single-model.md", "orchestrator-task-executor.md", "orchestrator-task-reviewer.md", "orchestrator-task-reviewer-single-model.md", "orchestrator-task-adjuster.md", "orchestrator-final-reviewer.md")
        mutation_commands = ("git add .", "git commit -m unsafe", "git reset --hard", "git checkout main", "git switch main", "git clean -fd", "git stash", "git merge topic", "git rebase main", "git push")
        for name in command_agents:
            rules = self.permission_rules(agents[name], "bash")
            self.assertEqual(self.evaluate(rules, "git diff --no-ext-diff --no-textconv --name-only --"), "allow", name)
            self.assertEqual(self.evaluate(rules, "git diff --no-ext-diff --no-textconv --check --"), "allow", name)
            for command in mutation_commands:
                self.assertEqual(self.evaluate(rules, command), "deny", f"{name}: {command}")
            for command in ("git diff --no-ext-diff --no-textconv -- src/app.py; git add .", "git diff --no-ext-diff --no-textconv -- src/app.py && git commit -m unsafe", "git diff --no-ext-diff --no-textconv -- src/app.py\ngit add .", "git diff --no-ext-diff --no-textconv -- src/app.py\rgit add ."):
                self.assertEqual(self.evaluate(rules, command), "deny", f"{name}: separator")
        for name in ("orchestrator-task-executor.md", "orchestrator-task-reviewer.md", "orchestrator-task-reviewer-single-model.md", "orchestrator-final-reviewer.md"):
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

    def test_update_preserves_unknown_plugins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            self.run_cli(ROOT, target, "install")
            unknown = target / "plugins/user-plugin.js"
            unknown.write_text("export default async () => ({})\n", encoding="utf-8")
            self.run_cli(ROOT, target, "update", "--backup-dir", str(backup))
            self.assertEqual(unknown.read_text(encoding="utf-8"), "export default async () => ({})\n")
            self.assertFalse(backup.exists())

    def test_update_preserves_preexisting_guard_plugin_collision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            plugin = target / "plugins/analyst-workflow-guard.js"
            plugin.parent.mkdir(parents=True)
            plugin.write_text("export default async () => ({})\n", encoding="utf-8")
            self.run_cli(ROOT, target, "install")
            self.run_cli(ROOT, target, "update", "--backup-dir", str(backup))
            self.assertEqual(plugin.read_text(encoding="utf-8"), "export default async () => ({})\n")
            self.assertFalse(backup.exists())

    def test_install_preflights_required_source_groups(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "config"
            (source / "agents").mkdir(parents=True)
            (source / "agents/example.md").write_text("agent\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(CLI), "--source", str(source), "--target", str(target), "install"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((target / "agents/example.md").exists())

    def test_install_rolls_back_added_files_on_write_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            original = OPENCODE_AGENTS.atomic_write
            calls = 0

            def failing_write(source, content, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("forced failure")
                original(source, content, destination)

            with patch.object(OPENCODE_AGENTS, "atomic_write", side_effect=failing_write):
                with self.assertRaisesRegex(OSError, "forced failure"):
                    OPENCODE_AGENTS.install(ROOT, target, False)
            self.assertEqual(list((target / "agents").glob("*.md")), [])
            self.assertFalse((target / "plugins/analyst-workflow-guard.js").exists())
            self.assertFalse((target / "AGENTS.md").exists())

    def test_update_backs_up_and_removes_retired_agent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            self.run_cli(ROOT, target, "install")
            retired = target / "agents/orchestrator-recon.md"
            fixture = ROOT / "tests/fixtures/orchestrator-recon-2.0.0.md"
            retired.write_bytes(fixture.read_bytes())
            status = self.run_cli(ROOT, target, "status", capture_output=True)
            self.assertIn("retired agents/orchestrator-recon.md", status.stdout)
            self.assertIn("retired=1", status.stdout)
            self.run_cli(ROOT, target, "update", "--backup-dir", str(backup))
            self.assertFalse(retired.exists())
            self.assertEqual((backup / "agents/orchestrator-recon.md").read_bytes(), fixture.read_bytes())

    def test_update_preserves_custom_agent_with_retired_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            self.run_cli(ROOT, target, "install")
            custom = target / "agents/orchestrator-recon.md"
            custom.write_text("custom\n", encoding="utf-8")
            self.run_cli(ROOT, target, "update", "--backup-dir", str(backup))
            self.assertEqual(custom.read_text(encoding="utf-8"), "custom\n")
            self.assertFalse(backup.exists())

    def test_update_restores_retired_agent_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            self.run_cli(ROOT, target, "install")
            retired = target / "agents/orchestrator-recon.md"
            fixture = ROOT / "tests/fixtures/orchestrator-recon-2.0.0.md"
            retired.write_bytes(fixture.read_bytes())
            with patch.object(OPENCODE_AGENTS, "rendered_global_instructions", side_effect=RuntimeError("forced failure")):
                with self.assertRaisesRegex(RuntimeError, "forced failure"):
                    OPENCODE_AGENTS.update(ROOT, target, backup, False)
            self.assertEqual(retired.read_bytes(), fixture.read_bytes())

    def test_status_and_global_caveman_guidance(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(ROOT, target, "install")
            result = self.run_cli(ROOT, target, "status", capture_output=True)
            self.assertIn("summary missing=0 changed=0 current=17 retired=0", result.stdout)
            instructions = (target / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(instructions.count(OPENCODE_AGENTS.GLOBAL_INSTRUCTIONS_START), 1)
            self.assertIn("caveman", instructions)

    def test_complete_github_api_source_installs_agents_and_plugins(self):
        files = [ROOT / "AGENTS.md", *sorted((ROOT / "agents").glob("*.md")), *sorted((ROOT / "plugins").glob("*.js"))]
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
            self.assertEqual(sorted(self.installed_plugins(target)), PLUGIN_NAMES)
            self.assertFalse((target / "protocols").exists())
            self.assertFalse((target / "helpers").exists())

    def test_runtime_plugin_regressions(self):
        subprocess.run(["node", "--test", str(ROOT / "tests/test-plugin.mjs")], check=True)

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
        self.assertTrue(OPENCODE_AGENTS.installable_repository_path("agents/example.md"))
        self.assertTrue(OPENCODE_AGENTS.installable_repository_path("plugins/example.js"))
        for path in ("agents/nested/example.md", "plugins/example.ts", "plugins/nested/example.js", "other/example.js"):
            self.assertFalse(OPENCODE_AGENTS.installable_repository_path(path))

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
