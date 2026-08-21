from __future__ import annotations

import json
from pathlib import Path
import re
import sys

from common import run, write_files


RELEASE_TEST = r'''
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
'''


def replace_section(source: str, start: str, end: str, replacement: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if pattern.search(source):
        return pattern.sub(replacement, source)
    return source.rstrip() + "\n\n" + replacement + "\n"


def apply(root: Path, log: Path, metadata_file: Path) -> list[str]:
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    commits = metadata["required_commits"]
    if len(commits) != 8 or any(not re.fullmatch(r"[0-9a-f]{40}", item) for item in commits):
        raise RuntimeError(f"release metadata requires the first eight exact commits: {commits}")
    code_ref = metadata["code_ref"]
    docs_ref = metadata["docs_ref"]
    matrix = metadata["matrix"]
    manifest = {
        "schema_version": 1,
        "release": "6.0.1",
        "branch": "agent/6.0.1-independent-hardening",
        "base_commit": "7b43e411bc87da8182fa1c0c7a972b005831a573",
        "python_6_0_snapshot": "0570ed9521c67eb21669479805f4c7bfdd1db743",
        "required_commits": commits,
        "immutable_installer_ref": code_ref,
        "documentation_ref": docs_ref,
        "architecture": {
            "semantic_agents": 4,
            "typescript_controllers": 1,
            "native_tools": 3,
            "python_controller": 0,
            "generic_workflow_framework": False,
            "external_service_or_database": False,
        },
        "gates": {
            "local_executable_gates": True,
            "cross_platform_matrix": True,
            "matrix_runs": matrix,
            "commands": ["npm ci", "npm test", "npm run typecheck", "npm run check:generated"],
            "complete_store_journey": True,
            "stale_input_output": True,
            "immutable_remote_install": True,
            "guarded_update": True,
            "legacy_validate_next": True,
            "nfr_adversarial": True,
            "impossible_states": True,
            "symlink_containment": True,
            "journal_conflict_recovery": True,
            "fresh_install_status_update": True,
        },
    }
    release_markdown = f'''# OpenCode Agents 6.0.1

Stable 6.0.1 is the independent-hardening release of the existing TypeScript architecture. It keeps four semantic agents, one TypeScript controller, and three native OpenCode tools; it does not add a Python controller, generic workflow framework, service, or database.

## Immutable runtime source

Installer and package tree are pinned to `{code_ref}`. Documentation gates are in `{docs_ref}` and `docs/RELEASE_GATES.md`.

## Executed gates

- exact dependency install: `npm ci`;
- full controller, native-tool, and installer baseline: `npm test`;
- actual plugin API: `npm run typecheck`;
- generated runtime: `npm run check:generated`;
- complete artifact-producing store journey;
- stale input/output, immutable remote installer, guarded retirement, legacy resume, NFR adversarial, impossible-state, symlink, and journal conflict/recovery tests;
- Linux, Windows, and macOS on Node 20 and 22.

The exact final-tree ZIP and SHA-256 are produced after this commit and stored on the dedicated artifact branch, so the archive cannot recursively alter the release tree it represents.
'''
    roadmap_path = root / "ROADMAP.md"
    roadmap = roadmap_path.read_text(encoding="utf-8")
    done = f'''<!-- 6.0.1-hardening:start -->
## ROADMAP DONE: 6.0.1 independent hardening

All executable local gates and the Linux/Windows/macOS × Node 20/22 matrix completed before this release commit. The machine-readable evidence is `release/6.0.1-gates.json`; the exact final-tree ZIP and SHA-256 are generated after the commit and attached through the artifact branch.

- Runtime/code ref: `{code_ref}`.
- Documentation ref: `{docs_ref}`.
- Architecture: four semantic agents, one TypeScript controller, three native tools.
<!-- 6.0.1-hardening:end -->'''
    roadmap = replace_section(roadmap, "<!-- 6.0.1-hardening:start -->", "<!-- 6.0.1-hardening:end -->", done)

    changed = write_files(root, {
        "VERSION": "6.0.1\n",
        "RELEASE.md": release_markdown,
        "ROADMAP.md": roadmap,
        "release/6.0.1-gates.json": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        "tests/test_release_metadata.py": RELEASE_TEST,
    })
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_release_metadata.py", "-v"], cwd=root, log=log)
    return changed


if __name__ == "__main__":
    repository = Path(sys.argv[1]).resolve()
    log = Path(sys.argv[2]).resolve()
    metadata_file = Path(sys.argv[3]).resolve()
    print("\n".join(apply(repository, log, metadata_file)))
