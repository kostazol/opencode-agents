
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseDocumentationTests(unittest.TestCase):
    def test_installer_and_package_tree_use_the_same_immutable_sha(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("5.1.1", readme)
        self.assertNotRegex(readme, r"raw\.githubusercontent\.com/[^\s]+/main/opencode-agents\.py")
        raw = re.search(r"raw\.githubusercontent\.com/kostazol/opencode-agents/([0-9a-f]{40})/opencode-agents\.py", readme)
        self.assertIsNotNone(raw)
        reference = re.search(r"--ref\s+([0-9a-f]{40})", readme)
        self.assertIsNotNone(reference)
        self.assertEqual(raw.group(1), reference.group(1))

    def test_release_claims_name_executable_gates(self):
        gates = (ROOT / "docs/RELEASE_GATES.md").read_text(encoding="utf-8")
        for command in ["npm ci", "npm test", "npm run typecheck", "npm run check:generated"]:
            self.assertIn(f"`{command}`", gates)
        for gate in ["complete store journey", "stale-input", "immutable remote install", "guarded retirement", "legacy validate", "nfr adversarial", "impossible-state", "symlink containment", "journal conflict"]:
            self.assertIn(gate, gates.lower())


if __name__ == "__main__":
    unittest.main()
