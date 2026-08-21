
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "opencode-agents.py"
VERSION = "6.0.1"
AGENTS = [
    "orchestrator-analyst.md",
    "orchestrator-discovery.md",
    "orchestrator-stage-planner.md",
    "orchestrator-stage-reviewer.md",
]

SPEC = importlib.util.spec_from_file_location("opencode_agents", CLI)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load installer")
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class InstallerTests(unittest.TestCase):
    def run_cli(self, target: Path, command: str, *extra: str, check: bool = True):
        arguments = [sys.executable, str(CLI), command, "--target", str(target)]
        if command != "status":
            arguments.extend(["--source", str(ROOT)])
        arguments.extend(extra)
        return subprocess.run(arguments, text=True, capture_output=True, check=check)

    def test_release_inventory(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(INSTALLER.VERSION, VERSION)
        self.assertEqual(package["version"], VERSION)
        self.assertEqual(sorted(path.name for path in (ROOT / "agents").glob("*.md")), AGENTS)
        self.assertTrue((ROOT / "tools/orchestrator.ts").is_file())
        self.assertTrue((ROOT / "runtime/orchestrator.js").is_file())
        self.assertTrue((ROOT / "runtime/orchestrator.d.ts").is_file())
        self.assertFalse((ROOT / "runtime/orchestrator.py").exists())
        self.assertFalse((ROOT / "orchestrator_core").exists())
        self.assertFalse((ROOT / "runtime/orchestrator_core").exists())

    def test_fresh_install_and_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            installed = self.run_cli(target, "install")
            self.assertEqual(installed.returncode, 0, installed.stderr)
            for relative in [
                "agents/orchestrator-analyst.md",
                "tools/orchestrator.ts",
                "runtime/orchestrator.js",
                "runtime/orchestrator.d.ts",
                ".opencode-agents-manifest.json",
            ]:
                self.assertTrue((target / relative).is_file(), relative)
            status = self.run_cli(target, "status", check=False)
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            payload = json.loads(status.stdout)
            self.assertTrue(payload["installed"])
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["missing"], [])
            self.assertEqual(payload["modified"], [])

    def test_second_install_is_rejected_and_update_replaces_with_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            self.run_cli(target, "install")
            analyst = target / "agents/orchestrator-analyst.md"
            analyst.write_text("local modification\n", encoding="utf-8")

            second_install = self.run_cli(target, "install", check=False)
            self.assertEqual(second_install.returncode, 2)
            self.assertIn("use update", second_install.stderr.lower())
            self.assertEqual(analyst.read_text(encoding="utf-8"), "local modification\n")

            self.run_cli(target, "update", "--backup", str(backup))
            self.assertEqual(analyst.read_bytes(), (ROOT / "agents/orchestrator-analyst.md").read_bytes())
            self.assertEqual((backup / "agents/orchestrator-analyst.md").read_text(encoding="utf-8"), "local modification\n")

    def test_update_preserves_unknown_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(target, "install")
            custom = target / "tools/custom.ts"
            custom.write_text("export const custom = true\n", encoding="utf-8")
            self.run_cli(target, "update")
            self.assertEqual(custom.read_text(encoding="utf-8"), "export const custom = true\n")


if __name__ == "__main__":
    unittest.main()
