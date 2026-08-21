
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_versions_and_release_gate_manifest_align(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / "release/6.0.1-gates.json").read_text(encoding="utf-8"))
        installer = (ROOT / "opencode-agents.py").read_text(encoding="utf-8")
        self.assertEqual(package["version"], "6.0.1")
        self.assertEqual((ROOT / "VERSION").read_text().strip(), "6.0.1")
        self.assertRegex(installer, r'VERSION\s*=\s*"6\.0\.1"')
        self.assertEqual(manifest["release"], "6.0.1")
        self.assertEqual(len(manifest["required_commits"]), 8)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in manifest["required_commits"]))
        self.assertTrue(manifest["gates"]["local_executable_gates"])
        self.assertTrue(manifest["gates"]["cross_platform_matrix"])
        self.assertNotIn("environment-blocked", manifest["gates"])

    def test_roadmap_done_claim_follows_recorded_gates(self):
        roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("ROADMAP DONE: 6.0.1 independent hardening", roadmap)
        self.assertIn("release/6.0.1-gates.json", roadmap)


if __name__ == "__main__":
    unittest.main()
