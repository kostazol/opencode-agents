
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("opencode_agents_installer_regression", ROOT / "opencode-agents.py")
installer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(installer)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def package(root: Path, marker: str) -> None:
    files = {
        "agents/orchestrator-discovery.md": f"agent {marker}\n".encode(),
        "agents/orchestrator-stage-planner.md": b"planner\n",
        "agents/orchestrator-stage-reviewer.md": b"reviewer\n",
        "agents/orchestrator-controller.md": b"controller\n",
        "runtime/orchestrator.js": f"export const marker = {marker!r}\n".encode(),
        "runtime/orchestrator.d.ts": b"export declare const marker: string\n",
        "tools/orchestrator.ts": b"export const tool = true\n",
    }
    for relative, content in files.items():
        candidate = root / relative
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(content)
    (root / installer.SOURCE_REF_NAME).write_text("a" * 40 + "\n", encoding="utf-8")


class InstallerRegressionTests(unittest.TestCase):
    def test_fresh_install_status_and_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source1 = base / "source1"
            source2 = base / "source2"
            target = base / "target"
            backup = base / "backup"
            source1.mkdir()
            source2.mkdir()
            package(source1, "one")
            package(source2, "two")

            installed = installer.install_or_update(source1, target)
            self.assertEqual(installed["operation"], "install")
            self.assertTrue(installer.status(target)["ok"])

            updated = installer.install_or_update(source2, target, update=True, backup=backup)
            self.assertEqual(updated["operation"], "update")
            self.assertTrue((backup / "runtime/orchestrator.js").exists())
            self.assertTrue(installer.status(target)["ok"])
            self.assertIn("two", (target / "runtime/orchestrator.js").read_text(encoding="utf-8"))

    def test_remote_install_resolves_ref_once_and_fetches_tree_and_blobs_by_commit(self):
        commit = "1" * 40
        contents = {
            "agents/orchestrator-discovery.md": b"discovery\n",
            "agents/orchestrator-stage-planner.md": b"planner\n",
            "agents/orchestrator-stage-reviewer.md": b"reviewer\n",
            "agents/orchestrator-controller.md": b"controller\n",
            "runtime/orchestrator.js": b"runtime\n",
            "runtime/orchestrator.d.ts": b"types\n",
            "tools/orchestrator.ts": b"tools\n",
        }
        entries = []
        blobs = {}
        for index, (path, content) in enumerate(contents.items()):
            sha = f"blob-{index}"
            entries.append({"path": path, "type": "blob", "sha": sha})
            blobs[sha] = {"encoding": "base64", "content": base64.b64encode(content).decode("ascii")}
        calls = []

        def fake_api(url):
            calls.append(url)
            if "/commits/" in url:
                return {"sha": commit}
            if url.endswith(f"/git/trees/{commit}?recursive=1"):
                return {"truncated": False, "tree": entries}
            for sha, blob in blobs.items():
                if url.endswith(f"/git/blobs/{sha}"):
                    return blob
            raise AssertionError(url)

        with patch.object(installer, "api_json", side_effect=fake_api):
            with installer.prepared_source(None, "owner/repo", "release-ref") as source:
                self.assertEqual((source / installer.SOURCE_REF_NAME).read_text().strip(), commit)
                self.assertTrue((source / "runtime/orchestrator.js").exists())
                self.assertTrue((source / "runtime/orchestrator.d.ts").exists())
        self.assertEqual(sum("/commits/" in call for call in calls), 1)
        self.assertTrue(any(f"/git/trees/{commit}" in call for call in calls))
        self.assertTrue(all("/main/" not in call for call in calls))

    def test_guarded_retirement_backs_up_known_python_6_and_preserves_customized_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            target = base / "target"
            backup = base / "backup"
            source.mkdir()
            package(source, "new")
            known = b"known python controller\n"
            customized = b"customized core\n"
            old = target / "runtime/orchestrator.py"
            custom = target / "runtime/orchestrator_core/custom.py"
            old.parent.mkdir(parents=True, exist_ok=True)
            custom.parent.mkdir(parents=True, exist_ok=True)
            old.write_bytes(known)
            custom.write_bytes(customized)
            manifests = {
                "runtime/orchestrator.py": {digest(known)},
                "runtime/orchestrator_core/custom.py": {digest(b"different known file\n")},
            }
            with patch.object(installer, "RETIREMENT_MANIFESTS", manifests):
                result = installer.install_or_update(source, target, update=True, backup=backup)
            self.assertFalse(old.exists())
            self.assertEqual(custom.read_bytes(), customized)
            self.assertEqual((backup / "runtime/orchestrator.py").read_bytes(), known)
            self.assertIn("runtime/orchestrator.py", result["retired_known"])
            self.assertIn("runtime/orchestrator_core/custom.py", result["preserved_customized"])

    def test_guarded_retirement_handles_known_5x_plugin_without_deleting_unknown_neighbor(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            target = base / "target"
            backup = base / "backup"
            source.mkdir()
            package(source, "new")
            managed = b"known managed plugin\n"
            unknown = b"unknown plugin\n"
            managed_path = target / "plugins/orchestrator-recovery.ts"
            unknown_path = target / "plugins/custom.ts"
            managed_path.parent.mkdir(parents=True, exist_ok=True)
            managed_path.write_bytes(managed)
            unknown_path.write_bytes(unknown)
            with patch.object(installer, "RETIREMENT_MANIFESTS", {"plugins/orchestrator-recovery.ts": {digest(managed)}}):
                installer.install_or_update(source, target, update=True, backup=backup)
            self.assertFalse(managed_path.exists())
            self.assertEqual(unknown_path.read_bytes(), unknown)
            self.assertEqual((backup / "plugins/orchestrator-recovery.ts").read_bytes(), managed)

    def test_target_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            target = base / "target"
            outside = base / "outside"
            source.mkdir()
            target.mkdir()
            outside.mkdir()
            package(source, "new")
            try:
                (target / "runtime").symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlinks unavailable: {error}")
            with self.assertRaises(installer.InstallerError):
                installer.install_or_update(source, target, update=True, backup=base / "backup")


if __name__ == "__main__":
    unittest.main()
