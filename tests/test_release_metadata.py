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
        self.assertEqual(package["engines"]["node"], "^22.22.2 || ^24.15.0")
        self.assertEqual((ROOT / "VERSION").read_text().strip(), "6.0.1")
        self.assertRegex(installer, r'VERSION\s*=\s*"6\.0\.1"')

        self.assertEqual(manifest["release"], "6.0.1")
        self.assertEqual(manifest["base_commit"], "5c897d5b3afba74940fcd188d2a2e13b21ebcc0b")
        self.assertEqual(manifest["branch"], "agent/6.0.1-final-complete")
        self.assertEqual(manifest["release_commit"], "6faaa57c637712059b89e2e2ca62b196c3a361aa")
        self.assertEqual(manifest["ci_commit"], "efdee043ddf792c52f90454b1224f375d2e84389")
        self.assertEqual(manifest["permanent_ci_workflow"], ".github/workflows/release-gates.yml")

        self.assertEqual(len(manifest["required_commits"]), 8)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in manifest["required_commits"]))
        self.assertTrue(manifest["gates"]["local_executable_gates"])
        self.assertTrue(manifest["gates"]["cross_platform_matrix"])
        self.assertNotIn("environment-blocked", manifest["gates"])

        matrices = manifest["gates"]["matrix_runs"]
        self.assertEqual([item["phase"] for item in matrices], ["implementation", "release-candidate", "final-release"])
        self.assertTrue(all(item["status"] == "passed" for item in matrices))
        self.assertTrue(all(item["node"] == [22, 24] for item in matrices))
        self.assertTrue(all(item["platforms"] == ["ubuntu-latest", "windows-latest", "macos-latest"] for item in matrices))

    def test_roadmap_done_claim_follows_recorded_gates(self):
        roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("ROADMAP DONE: 6.0.1 independent hardening", roadmap)
        self.assertIn("release/6.0.1-gates.json", roadmap)
        self.assertIn("agent/6.0.1-final-complete", roadmap)
        self.assertNotIn("attached through the artifact branch", roadmap)


if __name__ == "__main__":
    unittest.main()
