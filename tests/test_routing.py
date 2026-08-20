from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agents = {path.name: path.read_text(encoding="utf-8") for path in (ROOT / "agents").glob("*.md")}
        cls.analyst = cls.agents["orchestrator-analyst.md"]
        cls.discovery = cls.agents["orchestrator-discovery.md"]
        cls.planner = cls.agents["orchestrator-stage-planner.md"]
        cls.reviewer = cls.agents["orchestrator-stage-reviewer.md"]
        cls.tool = (ROOT / "tools/orchestrator.ts").read_text(encoding="utf-8")
        cls.runtime = (ROOT / "src/orchestrator.ts").read_text(encoding="utf-8")

    def test_prompts_and_docs_are_identical(self):
        for name, content in self.agents.items():
            self.assertEqual(content, (ROOT / "docs" / name).read_text(encoding="utf-8"), name)

    def test_capability_first_permissions(self):
        for content in self.agents.values():
            self.assertIn('  "*": ask', content)
            for capability in ("read", "edit", "glob", "grep", "list", "lsp", "bash", "todowrite"):
                self.assertIn(f"  {capability}: allow", content)
            self.assertIn('  "context7_*": allow', content)
        self.assertNotIn('  "*": deny', self.analyst)

    def test_primary_is_controller_client_not_manual_state_machine(self):
        for tool in ("orchestrator_next", "orchestrator_apply", "orchestrator_validate"):
            self.assertIn(f"  {tool}: allow", self.analyst)
        self.assertIn("# Единственный workflow loop", self.analyst)
        self.assertIn("Не вычисляй routing, revisions, reopening closure", self.analyst)
        self.assertNotIn("# Transition table", self.analyst)

    def test_semantic_roles_cover_traceability_and_independent_review(self):
        for token in ("REQ/NFR", "producer", "consumers", "NFR", "targeted tests/build"):
            self.assertIn(token, self.discovery)
        for mode in ("## DISCOVERY", "## TECHNICAL", "## HUMAN_REVIEW"):
            self.assertIn(mode, self.reviewer)
        self.assertIn('"evidence": [', self.reviewer)
        self.assertIn("controller читает файлы и вычисляет digest сам", self.reviewer)
        self.assertIn("owning `REQ/NFR/CON/AC/SCN`", self.planner)

    def test_native_typescript_tool_has_no_subprocess_bridge(self):
        self.assertIn('from "../runtime/orchestrator.js"', self.tool)
        for export in ("next", "apply", "validate"):
            self.assertIn(f"export const {export} = tool", self.tool)
        for forbidden in ("child_process", "spawn(", "python3", "runtime/orchestrator.py", "Bun."):
            self.assertNotIn(forbidden, self.tool)
        self.assertNotIn("Bun.", self.runtime)


if __name__ == "__main__":
    unittest.main()
