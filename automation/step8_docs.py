from __future__ import annotations

from pathlib import Path
import re
import sys

from common import expect_failure, run, write_files


DOC_TEST = r'''
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
        for gate in ["complete store journey", "stale-input", "immutable remote install", "guarded retirement", "legacy validate", "NFR adversarial", "impossible-state", "symlink containment", "journal conflict"]:
            self.assertIn(gate, gates.lower())


if __name__ == "__main__":
    unittest.main()
'''


def install_section(code_ref: str) -> str:
    return f'''<!-- 6.0.1-install:start -->
## Stable 6.0.1 immutable install

The controller remains four semantic agents, one TypeScript controller, and three native OpenCode tools. The installer and package tree below are both pinned to the same immutable Git commit; `main` is deliberately not used.

```bash
curl -fsSLO https://raw.githubusercontent.com/kostazol/opencode-agents/{code_ref}/opencode-agents.py
python opencode-agents.py install \\
  --repo kostazol/opencode-agents \\
  --ref {code_ref} \\
  --target ~/.config/opencode
python opencode-agents.py status --target ~/.config/opencode
```

For an update, use the same immutable source and an explicit backup location:

```bash
python opencode-agents.py update \\
  --repo kostazol/opencode-agents \\
  --ref {code_ref} \\
  --target ~/.config/opencode \\
  --backup ~/.config/opencode.backup-6.0.1
```
<!-- 6.0.1-install:end -->'''


GATES_DOC = r'''
# OpenCode Agents 6.0.1 executable release gates

The release architecture is intentionally narrow: four semantic agents, one TypeScript controller, and three native OpenCode tools. There is no parallel Python controller, generic workflow engine, external service, or database.

A claim is accepted only when the corresponding executable gate passes:

| Gate | Executable evidence |
|---|---|
| Exact dependency graph | `npm ci` |
| Controller and installer regression baseline | `npm test` |
| Real OpenCode plugin API | `npm run typecheck`; no local `tool: any` shim |
| Generated runtime | `npm run check:generated` and clean `git diff -- runtime` |
| Complete store journey | `tests-ts/journey.test.mjs` creates analysis, discovery, technical, human, and review artifacts before COMPLETE |
| stale-input and stale-output rejection | `tests-ts/release-blockers.test.mjs` and `tests-ts/controller-hardening.test.mjs` |
| immutable remote install | `tests/test_installer_hardening.py` and `tests/test_installer_regression.py` use mocked commit/tree/blob responses |
| guarded retirement | installer regression covers known Python 6.0 and managed 5.x hashes with mandatory backup and customized-file preservation |
| legacy validate → next | `tests-ts/legacy-resume-hardening.test.mjs` verifies lossless backup and explicit discovery continuation |
| NFR adversarial protocol | `tests-ts/nfr-adversarial.test.mjs` rejects duplicate, contradictory, unowned, and unlinked categories |
| impossible-state matrix | `tests-ts/routing-state-hardening.test.mjs` rejects illegal status, stage, human, and pending combinations |
| symlink containment | `tests-ts/release-gates.test.mjs` and installer symlink tests |
| journal conflict and recovery | `tests-ts/release-gates.test.mjs` |
| Cross-platform support | `.github/workflows/release-gates.yml`: Linux, Windows, macOS × Node 20, 22 |

The independent blocker workflow remains part of the branch. `opencode debug config grep` is not release evidence and is not used as a substitute for native tool invocation.
'''


def replace_section(source: str, start: str, end: str, replacement: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if pattern.search(source):
        return pattern.sub(replacement, source)
    return source.rstrip() + "\n\n" + replacement + "\n"


def roadmap(source: str, code_ref: str) -> str:
    section = f'''<!-- 6.0.1-hardening:start -->
## 6.0.1 independent hardening

- Architecture preserved: four semantic agents, one TypeScript controller, three native tools.
- Runtime/code commit: `{code_ref}`.
- Controller, routing, NFR protocol, legacy migration, installer, build, and regression gates are executable and documented in `docs/RELEASE_GATES.md`.
- Cross-platform matrix has passed for the runtime commit.
- Final-tree packaging, final matrix confirmation, and draft PR publication are release-finalization gates; this section intentionally does not claim ROADMAP DONE before they run.
<!-- 6.0.1-hardening:end -->'''
    return replace_section(source, "<!-- 6.0.1-hardening:start -->", "<!-- 6.0.1-hardening:end -->", section)


def apply(root: Path, log: Path, code_ref: str) -> list[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", code_ref):
        raise RuntimeError(f"invalid immutable code ref: {code_ref}")
    test_path = "tests/test_docs_release.py"
    changed = write_files(root, {test_path: DOC_TEST})
    expect_failure([sys.executable, "-m", "unittest", test_path.replace("/", ".").removesuffix(".py"), "-v"], cwd=root, log=log)

    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8").replace("5.1.1", "6.0.1")
    readme = re.sub(r"https://raw\.githubusercontent\.com/kostazol/opencode-agents/(?:main|v?6\.0\.1)/opencode-agents\.py", f"https://raw.githubusercontent.com/kostazol/opencode-agents/{code_ref}/opencode-agents.py", readme)
    readme = replace_section(readme, "<!-- 6.0.1-install:start -->", "<!-- 6.0.1-install:end -->", install_section(code_ref))

    roadmap_path = root / "ROADMAP.md"
    existing_roadmap = roadmap_path.read_text(encoding="utf-8") if roadmap_path.exists() else "# Roadmap\n"
    changed += write_files(root, {
        "README.md": readme,
        "ROADMAP.md": roadmap(existing_roadmap, code_ref),
        "docs/RELEASE_GATES.md": GATES_DOC,
    })
    run([sys.executable, "-m", "unittest", test_path.replace("/", ".").removesuffix(".py"), "-v"], cwd=root, log=log)
    return changed


if __name__ == "__main__":
    repository = Path(sys.argv[1]).resolve()
    log = Path(sys.argv[2]).resolve()
    code_ref = sys.argv[3]
    print("\n".join(apply(repository, log, code_ref)))
