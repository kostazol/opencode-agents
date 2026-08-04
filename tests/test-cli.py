import hashlib
import importlib.util
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "opencode-agents.py"
VERSION = "5.0.1"
AGENT_NAMES = [
    "orchestrator-analyst.md",
    "orchestrator-discovery.md",
    "orchestrator-stage-planner.md",
    "orchestrator-stage-reviewer.md",
]
RETIRED_411_AGENTS = {
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
}
SPEC = importlib.util.spec_from_file_location("opencode_agents", CLI)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load installer")
OPENCODE_AGENTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPENCODE_AGENTS)


class CliTests(unittest.TestCase):
    def run_cli(self, target: Path, command: str, *arguments: str, capture_output: bool = False):
        return subprocess.run([sys.executable, str(CLI), command, "--source", str(ROOT), "--target", str(target), *arguments], check=True, capture_output=capture_output, text=True)

    def agents(self, root: Path) -> dict[str, str]:
        return {path.name: path.read_text(encoding="utf-8") for path in sorted((root / "agents").glob("*.md"))}

    def test_release_markers_and_inventory(self):
        agents = self.agents(ROOT)
        self.assertEqual(sorted(agents), AGENT_NAMES)
        self.assertEqual(OPENCODE_AGENTS.VERSION, VERSION)
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), VERSION)
        self.assertEqual([name for name, content in agents.items() if re.search(r"^mode: primary$", content, re.MULTILINE)], ["orchestrator-analyst.md"])
        for name, content in agents.items():
            self.assertTrue(name.startswith("orchestrator-"))
            self.assertIn(f"# OpenCode Agents version: {VERSION}", content)
            self.assertIsNone(re.search(r"\b(?:never|do not|must not)\b|запрещ", content, re.IGNORECASE))

    def test_prompts_have_small_readable_contracts(self):
        agents = self.agents(ROOT)
        analyst = agents["orchestrator-analyst.md"]
        for name in ("orchestrator-discovery", "orchestrator-stage-planner", "orchestrator-stage-reviewer"):
            self.assertIn(f"    {name}: allow", analyst)
        for old_name in RETIRED_411_AGENTS:
            self.assertNotIn(f"    {old_name.removesuffix('.md')}: allow", analyst)
        self.assertIn("MODE: STEP", analyst)
        self.assertIn("one state transition", analyst)
        self.assertIn("first later stage that is not `PASS`", analyst)
        self.assertIn("DISCOVERY: QUESTIONS|READY_FOR_APPROVAL|BLOCKED", agents["orchestrator-discovery.md"])
        self.assertIn("STAGE_PLAN: REVIEW|MAP_CHANGE_REQUIRED|BLOCKED", agents["orchestrator-stage-planner.md"])
        self.assertIn("STAGE_REVIEW: PASS|REVISE|MAP_CHANGE_REQUIRED|BLOCKED", agents["orchestrator-stage-reviewer.md"])

    def test_permissions_match_role_boundaries(self):
        agents = self.agents(ROOT)
        self.assertIn('"1_orchestrator/*/plan.md": allow', agents["orchestrator-analyst.md"])
        self.assertIn('"1_orchestrator/*/questions.md": allow', agents["orchestrator-analyst.md"])
        self.assertIn('"1_orchestrator/*/discovery.md": allow', agents["orchestrator-discovery.md"])
        self.assertIn('"1_orchestrator/*/stages/*.md": allow', agents["orchestrator-stage-planner.md"])
        self.assertIn('"1_orchestrator/*/reviews/*.md": allow', agents["orchestrator-stage-reviewer.md"])
        self.assertIn("webfetch: ask", agents["orchestrator-discovery.md"])
        self.assertIn("webfetch: ask", agents["orchestrator-stage-planner.md"])
        self.assertIn("webfetch: ask", agents["orchestrator-stage-reviewer.md"])
        for name in ("orchestrator-discovery.md", "orchestrator-stage-planner.md", "orchestrator-stage-reviewer.md"):
            content = agents[name]
            self.assertIn('    "*": allow\n    "curl *": ask', content)
            self.assertIn('    "git push*": ask', content)
            self.assertIn('    "git add*": deny', content)
            self.assertIn("Keep product files and Git state unchanged", content)
        for content in agents.values():
            self.assertIn('external_directory: ask', content)
            self.assertIn('"*": deny', content)

    def test_fresh_install_and_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(target, "install")
            self.assertEqual(sorted(self.agents(target)), AGENT_NAMES)
            result = self.run_cli(target, "status", capture_output=True)
            self.assertIn("summary missing=0 changed=0 current=5 retired=0", result.stdout)

    def test_update_removes_known_file_with_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            self.run_cli(target, "install")
            retired = target / "agents/legacy.md"
            retired.write_text("managed legacy\n", encoding="utf-8")
            digest = hashlib.sha256(retired.read_bytes()).hexdigest()
            hashes = {Path("agents/legacy.md"): frozenset({digest})}
            with patch.object(OPENCODE_AGENTS, "RETIRED_FILE_HASHES", hashes):
                OPENCODE_AGENTS.update(ROOT, target, backup, False)
            self.assertFalse(retired.exists())
            self.assertEqual((backup / "agents/legacy.md").read_text(encoding="utf-8"), "managed legacy\n")

    def test_update_preserves_custom_retired_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            self.run_cli(target, "install")
            custom = target / "agents/orchestrator-executor.md"
            custom.write_text("custom\n", encoding="utf-8")
            self.run_cli(target, "update")
            self.assertEqual(custom.read_text(encoding="utf-8"), "custom\n")

    def test_all_411_agent_names_are_retired(self):
        retired = {str(path) for path in OPENCODE_AGENTS.RETIRED_FILE_HASHES}
        for name in RETIRED_411_AGENTS:
            self.assertIn(f"agents/{name}", retired)

    def test_status_reports_known_retired_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(target, "install")
            retired = target / "agents/orchestrator-executor.md"
            retired.write_bytes(b"legacy")
            digest = hashlib.sha256(b"legacy").hexdigest()
            hashes = {Path("agents/orchestrator-executor.md"): frozenset({digest})}
            output = StringIO()
            with patch.object(OPENCODE_AGENTS, "RETIRED_FILE_HASHES", hashes), redirect_stdout(output):
                OPENCODE_AGENTS.status(ROOT, target)
            self.assertIn("retired agents/orchestrator-executor.md", output.getvalue())


if __name__ == "__main__":
    unittest.main()
