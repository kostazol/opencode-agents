
from __future__ import annotations

import base64
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("opencode_agents_installer", ROOT / "opencode-agents.py")
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def complete_source(source: Path) -> None:
    files = {
        "agents/orchestrator-discovery.md": "discovery\n",
        "agents/orchestrator-stage-planner.md": "planner\n",
        "agents/orchestrator-stage-reviewer.md": "reviewer\n",
        "agents/orchestrator-controller.md": "controller\n",
        "runtime/orchestrator.js": "export {}\n",
        "runtime/orchestrator.d.ts": "export {}\n",
        "tools/orchestrator.ts": "export const tool = true\n",
    }
    for relative, content in files.items():
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")


class InstallerHardeningTests(unittest.TestCase):
    def test_top_level_runtime_javascript_and_declarations_are_installable(self) -> None:
        self.assertTrue(installer.installable("runtime/orchestrator.js"))
        self.assertTrue(installer.installable("runtime/orchestrator.d.ts"))
        self.assertTrue(installer.installable("runtime/state.js"))
        self.assertTrue(installer.installable("runtime/state.d.ts"))

    def test_remote_tree_and_blobs_are_resolved_from_one_immutable_commit(self) -> None:
        requested_ref = "release-6.0.1"
        commit_sha = "a" * 40
        js_content = b"export const ok=1\n"
        declaration_content = b"export declare const ok: 1\n"
        js_sha = git_blob_sha(js_content)
        declaration_sha = git_blob_sha(declaration_content)
        calls: list[str] = []
        original = installer.api_json

        def fake_api_json(url: str) -> dict:
            calls.append(url)
            if url.endswith(f"/repos/kostazol/opencode-agents/commits/{requested_ref}"):
                return {"sha": commit_sha}
            if url.endswith(f"/repos/kostazol/opencode-agents/git/trees/{commit_sha}?recursive=1"):
                return {
                    "sha": commit_sha,
                    "truncated": False,
                    "tree": [
                        {"path": "runtime/orchestrator.js", "type": "blob", "sha": js_sha, "size": len(js_content)},
                        {"path": "runtime/orchestrator.d.ts", "type": "blob", "sha": declaration_sha, "size": len(declaration_content)},
                    ],
                }
            if url.endswith(f"/repos/kostazol/opencode-agents/git/blobs/{js_sha}"):
                return {"encoding": "base64", "content": base64.b64encode(js_content).decode("ascii")}
            if url.endswith(f"/repos/kostazol/opencode-agents/git/blobs/{declaration_sha}"):
                return {"encoding": "base64", "content": base64.b64encode(declaration_content).decode("ascii")}
            raise AssertionError(f"unexpected mutable or unrelated GitHub request: {url}")

        installer.api_json = fake_api_json
        try:
            with installer.prepared_source(None, "kostazol/opencode-agents", requested_ref) as source:
                self.assertEqual((source / "runtime/orchestrator.js").read_bytes(), js_content)
                self.assertEqual((source / "runtime/orchestrator.d.ts").read_bytes(), declaration_content)
        finally:
            installer.api_json = original

        self.assertTrue(any(f"/commits/{requested_ref}" in call for call in calls))
        self.assertTrue(any(f"/git/trees/{commit_sha}?recursive=1" in call for call in calls))
        self.assertFalse(any("/git/trees/release-6.0.1" in call for call in calls))

    def test_known_python_and_managed_plugin_files_are_retired_with_backup(self) -> None:
        known = {
            "runtime/orchestrator.py": b"known Python 6.0 controller\n",
            "runtime/orchestrator_core/state.py": b"known Python 6.0 state\n",
            "plugins/orchestrator-recovery.ts": b"known managed 5.x plugin\n",
        }
        manifest = {
            relative: {hashlib.sha256(content).hexdigest()}
            for relative, content in known.items()
        }
        original_manifest = getattr(installer, "RETIREMENT_MANIFESTS", None)
        installer.RETIREMENT_MANIFESTS = manifest
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "source"
                target = root / "target"
                backup = root / "backup"
                complete_source(source)
                for relative, content in known.items():
                    destination = target / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)

                with redirect_stdout(io.StringIO()):
                    installer.install_or_update(source, target, True, backup, False)

                for relative, content in known.items():
                    self.assertFalse((target / relative).exists(), relative)
                    self.assertEqual((backup / relative).read_bytes(), content)
        finally:
            if original_manifest is None:
                delattr(installer, "RETIREMENT_MANIFESTS")
            else:
                installer.RETIREMENT_MANIFESTS = original_manifest

    def test_customized_and_unknown_retirement_candidates_are_preserved(self) -> None:
        expected = b"known managed content\n"
        custom = b"locally customized content\n"
        manifest = {"runtime/orchestrator.py": {hashlib.sha256(expected).hexdigest()}}
        original_manifest = getattr(installer, "RETIREMENT_MANIFESTS", None)
        installer.RETIREMENT_MANIFESTS = manifest
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "source"
                target = root / "target"
                backup = root / "backup"
                complete_source(source)
                candidate = target / "runtime/orchestrator.py"
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_bytes(custom)
                unknown = target / "runtime/orchestrator_core/custom.py"
                unknown.parent.mkdir(parents=True, exist_ok=True)
                unknown.write_text("custom\n", encoding="utf-8")

                with redirect_stdout(io.StringIO()):
                    installer.install_or_update(source, target, True, backup, False)

                self.assertEqual(candidate.read_bytes(), custom)
                self.assertEqual(unknown.read_text(encoding="utf-8"), "custom\n")
                self.assertFalse((backup / "runtime/orchestrator.py").exists())
        finally:
            if original_manifest is None:
                delattr(installer, "RETIREMENT_MANIFESTS")
            else:
                installer.RETIREMENT_MANIFESTS = original_manifest


if __name__ == "__main__":
    unittest.main()
