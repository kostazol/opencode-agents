import base64
from contextlib import redirect_stdout
import hashlib
import importlib.util
from io import StringIO
import json
import os
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
    "orchestrator-plan-ultra-reviewer.md",
    "orchestrator-stage-decomposer.md",
    "orchestrator-stage-pair-reviewer.md",
    "orchestrator-stage-question-reviewer.md",
    "orchestrator-task-adjuster.md",
    "orchestrator-task-executor.md",
    "orchestrator-task-planner.md",
    "orchestrator-task-reviewer.md",
]
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
E2E_PATH = ROOT / "tests/test-analyst-e2e.py"
E2E_SPEC = importlib.util.spec_from_file_location("analyst_e2e_test_helpers", E2E_PATH)
if E2E_SPEC is None or E2E_SPEC.loader is None:
    raise RuntimeError("cannot load tests/test-analyst-e2e.py")
ANALYST_E2E = importlib.util.module_from_spec(E2E_SPEC)
E2E_SPEC.loader.exec_module(ANALYST_E2E)
QUESTIONS_PATH = ROOT / "tests/test-analyst-questions-e2e.py"
QUESTIONS_SPEC = importlib.util.spec_from_file_location("analyst_questions_test_helpers", QUESTIONS_PATH)
if QUESTIONS_SPEC is None or QUESTIONS_SPEC.loader is None:
    raise RuntimeError("cannot load tests/test-analyst-questions-e2e.py")
ANALYST_QUESTIONS = importlib.util.module_from_spec(QUESTIONS_SPEC)
QUESTIONS_SPEC.loader.exec_module(ANALYST_QUESTIONS)


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
            self.assertEqual(plugins, {})
            self.assertFalse((target / "plugins").exists())
            self.assertEqual([name for name, content in agents.items() if re.search(r"^mode: primary$", content, re.MULTILINE)], ["orchestrator-analyst.md", "orchestrator-executor.md"])
            version = "4.1.1"
            self.assertEqual(OPENCODE_AGENTS.VERSION, version)
            for content in agents.values():
                self.assertNotRegex(content, r"__[A-Z][A-Z0-9_]+__")
                self.assertIn(f"# OpenCode Agents version: {version}", content)
                self.assertNotIn("protocols/orchestrator.md", content)
                self.assertNotIn("Read `__OPENCODE", content)
            self.assertFalse(any("workflow_certificate" in content for content in agents.values()))
            self.assertEqual(self.evaluate(self.permission_rules(agents["orchestrator-analyst.md"], "question"), "*"), "allow")
            self.assertFalse((target / "protocols").exists())
            self.assertFalse((target / "helpers").exists())

    def test_models_match_agents_only_architecture(self):
        source_agents = self.installed_agents(ROOT)
        pinned = {name for name, content in source_agents.items() if re.search(r"^model:", content, re.MULTILINE)}
        self.assertEqual(pinned, set(PINNED_AGENTS))
        for name, model in PINNED_AGENTS.items():
            self.assertIsNotNone(re.search(rf"^model: {re.escape(model)}$", source_agents[name], re.MULTILINE))
        for name in ("orchestrator-plan-reviewer.md", "orchestrator-stage-decomposer.md", "orchestrator-stage-pair-reviewer.md", "orchestrator-stage-question-reviewer.md", "orchestrator-task-executor.md", "orchestrator-task-planner.md", "orchestrator-task-reviewer.md"):
            self.assertIsNone(re.search(r"^model:", source_agents[name], re.MULTILINE))

    def test_live_harness_uses_official_isolation_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"OPENCODE_CONFIG": "bad", "OPENCODE_PERMISSION": "bad"}):
                environment = ANALYST_E2E.isolated_environment(root / "config-home/opencode", root, root / "data-home")
            for variable in ("OPENCODE_TEST_HOME", "OPENCODE_DISABLE_PROJECT_CONFIG", "OPENCODE_PURE", "OPENCODE_DISABLE_AUTOUPDATE", "OPENCODE_DISABLE_AUTOCOMPACT", "OPENCODE_DISABLE_MODELS_FETCH"):
                self.assertIn(variable, environment)
            self.assertNotIn("OPENCODE_CONFIG", environment)
            self.assertNotIn("OPENCODE_PERMISSION", environment)
            self.assertEqual(json.loads(environment["OPENCODE_CONFIG_CONTENT"]), {"model": ANALYST_E2E.MODEL})

    def test_live_harness_contract_helpers_are_deterministic(self):
        rejected = "PLANNING: REJECTED\nMODE: PLAN_STAGE\nRejection: missing input\nБлокер: none"
        self.assertEqual(ANALYST_E2E.intended_retry_subagent("orchestrator-plan-reviewer", rejected), "orchestrator-task-planner")
        self.assertEqual(ANALYST_E2E.contract_payload(f"<task_result>\n{rejected}\n</task_result>"), rejected)
        self.assertTrue(ANALYST_E2E.ambiguous_contract_output("orchestrator-plan-reviewer", rejected))
        self.assertTrue(ANALYST_E2E.equivalent_contract_identity(rejected, rejected))
        self.assertFalse(ANALYST_E2E.equivalent_contract_identity(rejected, rejected.replace("missing input", "changed finding")))
        self.assertTrue(ANALYST_E2E.equivalent_contract_identity(f"{rejected}\nCoverage checked: first wording", f"{rejected}\nCoverage checked: equivalent wording"))

    def test_live_harness_uses_v2_wait_and_questions(self):
        common = E2E_PATH.read_text(encoding="utf-8")
        questions = QUESTIONS_PATH.read_text(encoding="utf-8")
        self.assertIn('f"/api/session/{session_id}/wait"', common)
        self.assertIn('f"/api/session/{session_id}/question"', questions)
        self.assertIn('f"/api/session/{session_id}/question/{request_id}/reply"', questions)
        self.assertIn('f"/question/{request_id}/reply"', questions)

    def test_live_harness_wait_requires_successful_v2_wait(self):
        process = MagicMock()
        process.poll.return_value = None
        observed = {"ses_test": [{"info": {"role": "assistant"}, "parts": [{"type": "text", "text": "done"}]}]}
        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "server.log"
            log_path.write_text("", encoding="utf-8")
            with patch.object(ANALYST_E2E, "request_json", side_effect=[TimeoutError(), None]) as request, patch.object(ANALYST_E2E, "observe_session", return_value=(("progress",), None, observed)), patch.object(ANALYST_E2E, "fatal_log_failure", return_value=None):
                result = ANALYST_E2E.wait_for_session_idle("http://test", "ses_test", process, log_path, ANALYST_E2E.time.monotonic() + 5, 1)
            self.assertEqual(result, observed)
            self.assertEqual(request.call_count, 2)

    def test_live_harness_wait_falls_back_on_documented_503(self):
        process = MagicMock()
        process.poll.return_value = None
        observed = {"ses_test": [{"info": {"role": "assistant"}, "parts": [{"type": "text", "text": "done"}]}]}
        def request(_base_url, _method, path, body=None, timeout=30):
            if path.endswith("/wait"):
                raise RuntimeError("HTTP 503: Session wait is not available yet")
            if path == "/session/status":
                return {"ses_test": {"type": "idle"}}
            self.fail(path)
        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "server.log"
            log_path.write_text("", encoding="utf-8")
            with patch.object(ANALYST_E2E, "request_json", side_effect=request), patch.object(ANALYST_E2E, "observe_session", return_value=(("progress",), None, observed)), patch.object(ANALYST_E2E, "fatal_log_failure", return_value=None):
                result = ANALYST_E2E.wait_for_session_idle("http://test", "ses_test", process, log_path, ANALYST_E2E.time.monotonic() + 5, 1)
            self.assertEqual(result, observed)

    def test_live_harness_session_question_list_and_reply(self):
        process = MagicMock()
        process.poll.return_value = None
        request = {"id": "que_test", "sessionID": "ses_test", "questions": []}
        expected = {**request, "_transport": "v2"}
        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "server.log"
            log_path.write_text("", encoding="utf-8")
            with patch.object(ANALYST_E2E, "request_json", return_value={"data": [request]}), patch.object(ANALYST_E2E, "observe_session", return_value=(("progress",), None, {})), patch.object(ANALYST_E2E, "fatal_log_failure", return_value=None):
                self.assertEqual(ANALYST_QUESTIONS.wait_for_question(ANALYST_E2E, "http://test", "ses_test", process, log_path, ANALYST_E2E.time.monotonic() + 5), expected)
            with patch.object(ANALYST_E2E, "request_json", return_value=None) as reply:
                ANALYST_QUESTIONS.reply_to_question(ANALYST_E2E, "http://test", "ses_test", expected, [["answer"]])
            self.assertEqual(reply.call_args.args[2], "/api/session/ses_test/question/que_test/reply")

    def test_live_harness_legacy_question_fallback(self):
        process = MagicMock()
        process.poll.return_value = None
        request = {"id": "que_test", "sessionID": "ses_test", "questions": []}
        expected = {**request, "_transport": "legacy"}
        responses = [{"data": []}, [request]]
        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "server.log"
            log_path.write_text("", encoding="utf-8")
            with patch.object(ANALYST_E2E, "request_json", side_effect=responses), patch.object(ANALYST_E2E, "observe_session", return_value=(("progress",), None, {})), patch.object(ANALYST_E2E, "fatal_log_failure", return_value=None):
                self.assertEqual(ANALYST_QUESTIONS.wait_for_question(ANALYST_E2E, "http://test", "ses_test", process, log_path, ANALYST_E2E.time.monotonic() + 5), expected)
            with patch.object(ANALYST_E2E, "request_json", return_value=True) as reply:
                ANALYST_QUESTIONS.reply_to_question(ANALYST_E2E, "http://test", "ses_test", expected, [["answer"]])
            self.assertEqual(reply.call_args.args[2], "/question/que_test/reply")

    def test_live_harness_telemetry_aggregates_without_outputs(self):
        task = {"type": "tool", "tool": "task", "state": {"status": "completed", "input": {"subagent_type": "worker"}, "output": "secret-output", "time": {"start": 1000, "end": 3500}}}
        observed = {"ses_test": [{"info": {"role": "assistant", "tokens": {"input": 2, "output": 3, "reasoning": 4, "cache": {"read": 5, "write": 6}}}, "parts": [task]}], "ses_child": [{"info": {"tokens": {"input": 7, "output": 8, "reasoning": 9, "cache": {"read": 10, "write": 11}}}, "parts": []}]}
        output = StringIO()
        with patch.object(ANALYST_E2E, "observe_session", return_value=((), None, observed)), redirect_stdout(output):
            ANALYST_E2E.emit_timing_summary("test", "http://test", "ses_test", ANALYST_E2E.time.monotonic(), {})
        summary = output.getvalue()
        self.assertIn('"seconds": 2.5', summary)
        self.assertIn('"input": 9', summary)
        self.assertNotIn("secret-output", summary)

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
            self.assertIn("OpenCode configuration", content, name)
            self.assertIn("Do not quote upstream outputs or emit additional labeled contract fields", content, name)
        self.assertIn("`RESTAGE` is the only proposal eligible for approval", decomposer)
        self.assertIn("INITIAL is discovery round `0`", decomposer)
        self.assertIn("DISCOVERY requires exact accepted parent and full chain", decomposer)
        self.assertIn("Require round exactly parent + 1", decomposer)
        self.assertIn("`Question batch ID` repeats the producing answered batch", decomposer)
        self.assertIn("Decomposer never assigns a future question-review, batch, or question ID", decomposer)
        self.assertIn("RESTAGE requires full accepted discovery chain", decomposer)
        self.assertIn("exact terminal `PASS_NO_QUESTIONS` tied to latest discovery", decomposer)
        self.assertIn("Preserve latest discovery round and ID in RESTAGE output", decomposer)
        self.assertIn("Re-check evidence and regenerate stages rather than confirming the latest provisional proposal", decomposer)
        self.assertIn("obtain installed runtime version with exact `opencode --version`", decomposer)
        self.assertIn("Never treat a project `@opencode-ai/plugin` package version as installed OpenCode runtime version", decomposer)
        self.assertIn("do not ask user or block merely because local `node_modules`, a checked-in runtime catalog, or a direct-invocation fixture is absent", decomposer)
        self.assertIn("exact latest accepted `INITIAL|DISCOVERY` decomposition", question_reviewer)
        self.assertIn("not resolvable from request, cumulative decisions, evidence, conventions, or lowest-scope reversible defaults", question_reviewer)
        self.assertIn("Never repeat a cumulative decision or reuse any prior batch/question ID", question_reviewer)
        self.assertIn("no fixed limit exists on batches or total questions", question_reviewer)
        self.assertIn("Missing local `node_modules` or a checked-in runtime catalog is not a user question", question_reviewer)
        self.assertIn("ready for one native `question` call", question_reviewer)
        self.assertIn("Plan only supplied current stage", planner)
        self.assertIn("Do not create, edit, rename, supersede, or delete tasks belonging to another stage", planner)
        self.assertIn("Earlier-stage PASS output is authoritative while task metadata intentionally remains `DRAFT/PENDING`", planner)
        self.assertIn("requires delegation, exact calls, or another integration fact not proven by outputs alone", planner)
        self.assertIn("require a deterministic test proving the same error object escapes", planner)
        self.assertIn("Successful FINALIZE response is always `PLANNING: PASS`", planner)
        self.assertIn("approved RESTAGE containing terminal discovery ID, terminal question-review ID, and cumulative decisions", planner)
        self.assertIn("Never infer runtime version from `@opencode-ai/plugin`", planner)
        self.assertIn("Missing local `node_modules`, a checked-in runtime catalog, direct-invocation fixture", planner)
        self.assertIn("Fresh independent review of exactly one current stage", stage_reviewer)
        self.assertIn("approved RESTAGE with terminal discovery/question-review identities and cumulative decisions", stage_reviewer)
        self.assertIn("Do not demand checked-in `node_modules`, runtime catalog output, direct-invocation fixture", stage_reviewer)
        self.assertIn("Review whole stage", stage_reviewer)
        self.assertIn("never require upstream `READY/PASS` before FINALIZE", stage_reviewer)
        self.assertIn("future execution gate with current planning metadata", stage_reviewer)
        self.assertIn("exactly one adjacent pair", pair_reviewer)
        self.assertIn("approved RESTAGE with terminal discovery/question-review identities and cumulative decisions", pair_reviewer)
        self.assertIn("never treat that metadata as conflict or require `READY/PASS`", pair_reviewer)
        self.assertIn("`BACKTRACK_AUTHORITY`", ultra)
        self.assertIn("approved RESTAGE with terminal discovery/question-review identities and cumulative decisions", ultra)
        self.assertEqual(self.evaluate(self.permission_rules(ultra, "grep"), "src/Program.cs"), "deny")

    def test_primary_staged_workflow_order_and_backtracking(self):
        analyst = (ROOT / "agents/orchestrator-analyst.md").read_text(encoding="utf-8")
        initial = analyst.index("Dispatch fresh stage decomposer in `INITIAL` mode")
        questions = analyst.index("Dispatch fresh question reviewer against exact latest accepted `INITIAL|DISCOVERY`")
        discovery = analyst.index("dispatch fresh decomposer in `DISCOVERY`", questions)
        restage = analyst.index("dispatch fresh decomposer in `RESTAGE`", discovery)
        approval = analyst.index("Present authoritative request, all cumulative decisions or `none`, and complete ordered proposal")
        self.assertLess(initial, questions)
        self.assertLess(questions, discovery)
        self.assertLess(discovery, restage)
        self.assertLess(restage, approval)
        self.assertIn("After every task result, immediately make next required task or question call", analyst)
        self.assertIn("No progress-only text during autonomous flow", analyst)
        self.assertIn("Include all phase-available authoritative state, never nonexistent future state", analyst)
        self.assertIn("Copy every required request, discovery, question-review, RESTAGE, approval, planner, and reviewer output completely and verbatim", analyst)
        self.assertIn("full verbatim text of INITIAL and every accepted DISCOVERY in order", analyst)
        self.assertIn("an ID/decision ledger plus latest output is not a substitute", analyst)
        self.assertIn("Every task prompt contains exact labeled values", analyst)
        self.assertIn("copy immutable identity strings from latest accepted output rather than memory", analyst)
        self.assertIn("never forward rejected output as authority", analyst)
        self.assertIn("Permit at most three such `REJECTED` retries across one workflow", analyst)
        self.assertIn("No fixed limit exists for number of batches or total questions", analyst)
        self.assertIn("Accepted RESTAGE closes discovery and questions", analyst)
        self.assertIn("After RESTAGE PASS, never dispatch question reviewer, `DISCOVERY`, or native `question`", analyst)
        self.assertIn("A changed request invalidates proposal and restarts CREATE/REASSESS with a new discovery lineage", analyst)
        self.assertIn("erase stale approval state and never present, accept, or dispatch the older ID", analyst)
        self.assertIn("in `BACKTRACK_AUTHORITY` only", analyst)
        self.assertIn("Sol is not called for whole-plan final review", analyst)
        self.assertIn("call planner `FINALIZE`", analyst)
        self.assertIn("Treat each accepted subagent contract status as routing data", analyst)
        self.assertIn("never report a repairable `REVISE` as `BLOCKED`", analyst)
        self.assertIn("paste the approved RESTAGE as one untouched contiguous block", analyst)
        self.assertIn("selected-field reconstruction is malformed even when omitted values are `none`", analyst)
        self.assertIn("Never omit a field already present in upstream output", analyst)
        self.assertIn("Rebuild the retry prompt from complete authoritative state", analyst)
        self.assertIn("include the exact rejected output as diagnostic evidence", analyst)
        self.assertIn("If latest accepted status is nonterminal or says `Блокер: none`", analyst)
        self.assertIn("after one accepted status for a logical phase, never call that same role/phase/revision again", analyst)
        self.assertIn("Use exactly these next transitions for accepted statuses", analyst)
        self.assertIn("Never redispatch the producer of an accepted status", analyst)
        self.assertIn("A pair may be reviewed only by `orchestrator-stage-pair-reviewer`", analyst)
        self.assertIn("wrong-role or wrong-contract output is malformed and must be corrected", analyst)
        self.assertIn("wrong-role dispatch requires the intended role", analyst)
        self.assertIn("a one-stage plan has no pair and dispatches `FINALIZE` directly", analyst)
        self.assertIn("`MODE: INVALIDATE_SUFFIX` dispatches `BACKTRACK_STAGE`", analyst)
        self.assertIn("`REVISE` requires immediate same-turn planner `REVISE_STAGE`", (ROOT / "agents/orchestrator-plan-reviewer.md").read_text(encoding="utf-8"))
        self.assertIn("`REVISE_RIGHT`, `MINOR_LEFT`, and `SUBSTANTIVE_LEFT` require immediate same-turn corrective routing", (ROOT / "agents/orchestrator-stage-pair-reviewer.md").read_text(encoding="utf-8"))
        self.assertIn("`AUTHORIZED` and `DENIED` both require immediate same-turn planner/review continuation", (ROOT / "agents/orchestrator-plan-ultra-reviewer.md").read_text(encoding="utf-8"))
        self.assertIn("`REJECTED` means primary must correct payload and retry this same role/mode", (ROOT / "agents/orchestrator-task-planner.md").read_text(encoding="utf-8"))
        self.assertIn("reject selected-field reconstruction before any read or edit", (ROOT / "agents/orchestrator-task-planner.md").read_text(encoding="utf-8"))
        self.assertIn("RESTAGE and planner inputs must be contiguous verbatim contract blocks", (ROOT / "agents/orchestrator-plan-reviewer.md").read_text(encoding="utf-8"))
        self.assertIn("Mandatory harness fields and executor safety invariants from planner task shape", (ROOT / "agents/orchestrator-plan-reviewer.md").read_text(encoding="utf-8"))

    def test_executor_and_workflow_base_contracts_are_preserved(self):
        executor = (ROOT / "agents/orchestrator-executor.md").read_text(encoding="utf-8")
        adjuster = (ROOT / "agents/orchestrator-task-adjuster.md").read_text(encoding="utf-8")
        for field in ("Finding:", "Source:", "Cycle:", "Ordinary repair attempt:", "Status:", "Evidence:", "Requirement:", "Scope impact:", "Supersedes:"):
            self.assertIn(field, executor)
            self.assertIn(field, adjuster)
        self.assertIn("Do not expose or quote journals", executor)
        self.assertIn("Only workflow-designated task-correction authority can expand scope", (ROOT / "agents/orchestrator-task-executor.md").read_text(encoding="utf-8"))
        workflow_base_agents = tuple(AGENT_NAMES)
        for name in workflow_base_agents:
            content = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("WORKFLOW_BASE", content, name)
        for name in ("orchestrator-analyst.md",):
            content = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("Capture OpenCode session working directory as immutable `WORKFLOW_BASE`", content)
            self.assertIn("never substitute Git root, repository root, parent, or subagent directory", content)
        for name in ("orchestrator-executor.md",):
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
        git_prefix_consumers = ("orchestrator-task-executor.md", "orchestrator-task-reviewer.md", "orchestrator-task-adjuster.md", "orchestrator-final-reviewer.md")
        for name in git_prefix_consumers:
            content = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("WORKFLOW_GIT_PREFIX", content, name)
            self.assertIn("WORKFLOW_PRODUCT_GIT_PREFIX", content, name)
            self.assertIn("Git-root substitution only when root differs from `WORKFLOW_BASE`", content, name)
        for name in ("orchestrator-task-reviewer.md", "orchestrator-final-reviewer.md"):
            content = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("excluding only Git paths under exact `WORKFLOW_GIT_PREFIX`", content, name)
            self.assertIn("outside-prefix path", content, name)

    def test_reassessment_contracts_are_preserved(self):
        planner = (ROOT / "agents/orchestrator-task-planner.md").read_text(encoding="utf-8")
        for name in ("orchestrator-analyst.md",):
            analyst = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("Use `REASSESS` only when user explicitly supplies all three", analyst, name)
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
        for name in ("orchestrator-executor.md",):
            executor = (ROOT / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("Reject `DRAFT`, `SUPERSEDED`, and `COMPLETE`", executor)

    def test_native_question_without_certificate_or_plugin(self):
        agents = self.installed_agents(ROOT)
        for name, content in agents.items():
            self.assertNotIn("workflow_certificate", content, name)
        analyst = agents["orchestrator-analyst.md"]
        self.assertEqual(self.evaluate(self.permission_rules(analyst, "question"), "*"), "allow")
        self.assertIn("make one native `question` call for that review's complete current batch", analyst)
        self.assertIn("No fixed limit exists for number of batches or total questions", analyst)
        self.assertIn("generation remains reserved for post-approval Sol amendments, never discovery rounds", analyst)
        self.assertFalse((ROOT / "plugins/analyst-workflow-guard.js").exists())

    def test_opencode_runtime_discovery_is_least_privileged(self):
        agents = self.installed_agents(ROOT)
        runtime_agents = ("orchestrator-stage-decomposer.md", "orchestrator-task-planner.md", "orchestrator-plan-reviewer.md")
        for name in runtime_agents:
            bash_rules = self.permission_rules(agents[name], "bash")
            self.assertEqual(self.evaluate(bash_rules, "opencode --version"), "allow", name)
            self.assertEqual(self.evaluate(bash_rules, "opencode debug config"), "deny", name)
            self.assertEqual(self.evaluate(bash_rules, "git status"), "deny", name)
        for name in runtime_agents:
            webfetch_rules = self.permission_rules(agents[name], "webfetch")
            self.assertEqual(self.evaluate(webfetch_rules, "https://opencode.ai/docs/custom-tools/"), "allow", name)
            self.assertEqual(self.evaluate(webfetch_rules, "https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/plugin/src/tool.ts"), "allow", name)
        self.assertEqual(self.evaluate(self.permission_rules(agents["orchestrator-stage-question-reviewer.md"], "webfetch"), "https://opencode.ai/docs/custom-tools/"), "deny")

    def test_live_analyst_e2e_is_mandatory(self):
        commands = ("python3 tests/test-analyst-e2e.py", "python3 tests/test-analyst-questions-e2e.py", "python3 tests/test-analyst-replanning-e2e.py")
        for command in commands:
            self.assertTrue((ROOT / command.split()[-1]).is_file())
            self.assertIn(command, (ROOT / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertIn(command, (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn("After any change", (ROOT / "AGENTS.md").read_text(encoding="utf-8"))

    def test_primary_task_allowlists_are_exact(self):
        agents = self.installed_agents(ROOT)
        expected = {
            "orchestrator-analyst.md": {"orchestrator-stage-decomposer", "orchestrator-stage-question-reviewer", "orchestrator-task-planner", "orchestrator-plan-reviewer", "orchestrator-stage-pair-reviewer", "orchestrator-plan-ultra-reviewer"},
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
        for name in ("orchestrator-analyst.md",):
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "edit"), "1_orchestrator/request/tasks/01-task.md"), "deny")
        executor_edits = self.permission_rules(agents["orchestrator-task-executor.md"], "edit")
        self.assertEqual(self.evaluate(executor_edits, "src/Program.cs"), "allow")
        self.assertEqual(self.evaluate(executor_edits, ".git"), "deny")
        self.assertEqual(self.evaluate(executor_edits, ".git/index"), "deny")
        self.assertEqual(self.evaluate(executor_edits, "repo/.git/config"), "deny")
        self.assertEqual(self.evaluate(executor_edits, "1_orchestrator/request/tasks/01-task.md"), "deny")
        for name in ("orchestrator-executor.md",):
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "read"), "1_orchestrator/request/tasks/01-task.md"), "allow")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "glob"), "1_orchestrator/request/tasks/*.md"), "allow")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "edit"), "1_orchestrator/request/tasks/01-task.md"), "allow")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "read"), "../1_orchestrator/request/tasks/01-task.md"), "deny")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "glob"), "../1_orchestrator/request/tasks/*.md"), "deny")
            self.assertEqual(self.evaluate(self.permission_rules(agents[name], "edit"), "../1_orchestrator/request/tasks/01-task.md"), "deny")
        for name in ("orchestrator-analyst.md",):
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

    def test_update_preserves_unknown_plugins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            self.run_cli(ROOT, target, "install")
            unknown = target / "plugins/user-plugin.js"
            unknown.parent.mkdir()
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

    def test_install_requires_only_agents_source_group(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "config"
            (source / "agents").mkdir(parents=True)
            (source / "agents/example.md").write_text("agent\n", encoding="utf-8")
            self.run_cli(source, target, "install")
            self.assertEqual((target / "agents/example.md").read_text(encoding="utf-8"), "agent\n")
            self.assertFalse((target / "plugins").exists())

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

    def test_update_backs_up_and_removes_all_301_retired_files(self):
        retired_paths = (
            "plugins/analyst-workflow-guard.js",
            "agents/orchestrator-analyst-single-model.md",
            "agents/orchestrator-executor-single-model.md",
            "agents/orchestrator-task-reviewer-single-model.md",
        )
        self.assertTrue({Path(path) for path in retired_paths}.issubset(OPENCODE_AGENTS.RETIRED_FILE_HASHES))
        self.assertTrue(all(OPENCODE_AGENTS.RETIRED_FILE_HASHES[Path(path)] for path in retired_paths))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            self.run_cli(ROOT, target, "install")
            released = {relative: f"released {relative}\n".encode() for relative in retired_paths}
            retired_hashes = dict(OPENCODE_AGENTS.RETIRED_FILE_HASHES)
            for relative in retired_paths:
                content = released[relative]
                retired_hashes[Path(relative)] = frozenset((*retired_hashes[Path(relative)], hashlib.sha256(content).hexdigest()))
                path = target / relative
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(content)
            with patch.object(OPENCODE_AGENTS, "RETIRED_FILE_HASHES", retired_hashes):
                output = StringIO()
                with redirect_stdout(output):
                    OPENCODE_AGENTS.status(ROOT, target)
                self.assertIn("retired=4", output.getvalue())
                OPENCODE_AGENTS.update(ROOT, target, backup, False)
            for relative, content in released.items():
                self.assertFalse((target / relative).exists())
                self.assertEqual((backup / relative).read_bytes(), content)

    def test_update_preserves_custom_collisions_for_all_retired_301_names(self):
        retired_paths = (
            "plugins/analyst-workflow-guard.js",
            "agents/orchestrator-analyst-single-model.md",
            "agents/orchestrator-executor-single-model.md",
            "agents/orchestrator-task-reviewer-single-model.md",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            self.run_cli(ROOT, target, "install")
            for relative in retired_paths:
                path = target / relative
                path.parent.mkdir(exist_ok=True)
                path.write_text(f"custom {relative}\n", encoding="utf-8")
            self.run_cli(ROOT, target, "update", "--backup-dir", str(backup))
            for relative in retired_paths:
                self.assertEqual((target / relative).read_text(encoding="utf-8"), f"custom {relative}\n")
            self.assertFalse(backup.exists())

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
            self.assertIn("summary missing=0 changed=0 current=13 retired=0", result.stdout)
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
            self.assertEqual(self.installed_plugins(target), {})
            self.assertFalse((target / "plugins").exists())
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
        self.assertTrue(OPENCODE_AGENTS.installable_repository_path("agents/example.md"))
        for path in ("agents/nested/example.md", "plugins/example.js", "plugins/example.ts", "plugins/nested/example.js", "other/example.js"):
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

    @unittest.skipIf(sys.platform == "win32", "symlink behavior differs on Windows")
    def test_symlink_plugin_group_is_rejected_even_for_agents_only_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            outside = root / "outside"
            target.mkdir()
            outside.mkdir()
            (target / "plugins").symlink_to(outside, target_is_directory=True)
            result = subprocess.run([sys.executable, str(CLI), "--source", str(ROOT), "--target", str(target), "install"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("target group is not a directory", result.stderr)
            self.assertEqual(list(outside.iterdir()), [])

if __name__ == "__main__":
    unittest.main()
