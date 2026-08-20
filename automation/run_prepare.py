from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

import common
import step2_controller
import step3_routing
import step4_protocol
import step5_migration
import step6_installer
import step7_build
import step7_fixups
import step7_runtime


BASE_COMMIT = "7b43e411bc87da8182fa1c0c7a972b005831a573"
PYTHON_SNAPSHOT = "0570ed9521c67eb21669479805f4c7bfdd1db743"
COMMIT_ONE = common.BASELINE_SHA


def clean_generated_noise(root: Path, *, remove_dist_tools: bool = False) -> None:
    for candidate in root.rglob("__pycache__"):
        if candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)
    for candidate in root.rglob("*.pyc"):
        candidate.unlink(missing_ok=True)
    for relative in [".pytest_cache", ".mypy_cache"]:
        shutil.rmtree(root / relative, ignore_errors=True)
    if remove_dist_tools:
        shutil.rmtree(root / "dist-tools", ignore_errors=True)


def ensure_gitignore(root: Path) -> str:
    candidate = root / ".gitignore"
    existing = candidate.read_text(encoding="utf-8") if candidate.exists() else ""
    lines = existing.replace("\r\n", "\n").splitlines()
    required = ["node_modules/", "dist-tools/", "__pycache__/", "*.pyc"]
    for item in required:
        if item not in lines:
            lines.append(item)
    content = "\n".join(lines).strip("\n") + "\n"
    candidate.write_text(content, encoding="utf-8", newline="\n")
    return ".gitignore"


def patch_legacy_mode(root: Path) -> None:
    candidate = root / "src/routing.ts"
    source = candidate.read_text(encoding="utf-8")
    old = 'mode: correction ? "CORRECTION" : next.analysis_revision === 1 ? "INITIAL" : next.legacy_migrated ? "LEGACY_MIGRATION" : "FOLLOW_UP",'
    new = 'mode: correction ? "CORRECTION" : next.legacy_migrated ? "LEGACY_MIGRATION" : next.analysis_revision === 1 ? "INITIAL" : "FOLLOW_UP",'
    if old not in source:
        raise RuntimeError("legacy migration mode expression was not found exactly once")
    candidate.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")


def patch_installer_template() -> None:
    template = step6_installer.INSTALLER
    template = template.replace("from dataclasses import dataclass\n", "")
    if "import sys\n" not in template:
        template = template.replace("import stat\n", "import stat\nimport sys\n", 1)
    old = '''@dataclass(frozen=True)
class FileRecord:
    path: str
    sha256: str
    size: int
'''
    new = '''class FileRecord:
    def __init__(self, path: str, sha256: str, size: int) -> None:
        self.path = path
        self.sha256 = sha256
        self.size = size
'''
    if old not in template:
        raise RuntimeError("installer FileRecord template was not found")
    step6_installer.INSTALLER = template.replace(old, new, 1)


def patch_release_gate_fixture(root: Path) -> None:
    candidate = root / "tests-ts/release-gates.test.mjs"
    source = candidate.read_text(encoding="utf-8")
    old = '''  const conflictTarget = structuredClone(target)
  conflictTarget.state_revision = 3
'''
    new = '''  const conflictTarget = structuredClone(target)
  conflictTarget.state_revision = 3
  conflictTarget.pending.issued_state_revision = 3
'''
    if old not in source:
        raise RuntimeError("transaction conflict fixture was not found")
    candidate.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")


def report_commit(summary: Path | None, item: dict[str, object]) -> None:
    line = f"- `{item['sha']}` — {item['message']} — {', '.join(item['checks'])}\n"
    print(line, end="")
    if summary:
        with summary.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)


def commit_stage(
    root: Path,
    message: str,
    allowed: list[str],
    checks: list[str],
    log: Path,
    commits: list[dict[str, object]],
    summary: Path | None,
) -> str:
    clean_generated_noise(root)
    sha = common.commit_and_push(root, message, allowed, log=log)
    item: dict[str, object] = {"message": message, "sha": sha, "checks": checks}
    commits.append(item)
    report_commit(summary, item)
    return sha


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: run_prepare.py <automation-checkout> <target-checkout> <result-dir>")
    automation_root = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    result_dir = Path(sys.argv[3]).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    logs = result_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    summary = Path(os.environ["GITHUB_STEP_SUMMARY"]) if os.environ.get("GITHUB_STEP_SUMMARY") else None

    common.run(["git", "config", "user.name", "OpenCode Agents Release Bot"], cwd=root)
    common.run(["git", "config", "user.email", "opencode-agents-release@users.noreply.github.com"], cwd=root)
    common.run(["git", "fetch", "origin", common.TARGET_BRANCH, "--tags", "--force"], cwd=root)
    head = common.run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    parent = common.run(["git", "rev-parse", "HEAD^"], cwd=root).stdout.strip()
    grandparent = common.run(["git", "rev-parse", "HEAD^^"], cwd=root).stdout.strip()
    remote = common.run(["git", "ls-remote", "origin", f"refs/heads/{common.TARGET_BRANCH}"], cwd=root).stdout.split()[0]
    if head != COMMIT_ONE or remote != COMMIT_ONE or parent != BASE_COMMIT or grandparent != PYTHON_SNAPSHOT:
        raise RuntimeError(
            f"target history mismatch: head={head}, remote={remote}, parent={parent}, grandparent={grandparent}"
        )
    common.assert_clean(root)

    baseline_log = logs / "01-red-baseline.log"
    common.expect_failure(["node", "--test", "tests-ts/release-blockers.test.mjs"], cwd=root, log=baseline_log)
    common.expect_failure(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_installer_hardening.py", "-v"],
        cwd=root,
        log=baseline_log,
    )

    commits: list[dict[str, object]] = [
        {
            "message": "test: capture independent 6.0 release blockers",
            "sha": COMMIT_ONE,
            "checks": ["red controller blocker baseline", "red installer blocker baseline"],
        }
    ]
    report_commit(summary, commits[0])

    log = logs / "02-controller.log"
    step2_controller.apply(root, log)
    commit_stage(
        root,
        "fix(controller): enforce artifact contracts and stale-input protection",
        ["src", "runtime", "types", "tests-ts/controller-hardening.test.mjs"],
        ["artifact contracts", "pending input snapshots", "stale input/output negatives", "state schema migration"],
        log,
        commits,
        summary,
    )

    log = logs / "03-routing.log"
    step3_routing.apply(root, log)
    commit_stage(
        root,
        "fix(routing): pass correction sources and enforce legal state invariants",
        ["src/routing.ts", "src/state.ts", "runtime", "tests-ts/routing-state-hardening.test.mjs"],
        ["discovery/technical/human correction sources", "legal-state matrix", "impossible-state negatives"],
        log,
        commits,
        summary,
    )

    log = logs / "04-protocol.log"
    step4_protocol.apply(root, log)
    commit_stage(
        root,
        "fix(protocol): strengthen NFR applicability and traceability",
        ["src/analysis.ts", "runtime", "tests-ts/nfr-adversarial.test.mjs"],
        ["duplicate and contradictory categories", "required owner/NFR/acceptance traceability", "semantic fingerprint"],
        log,
        commits,
        summary,
    )

    log = logs / "05-migration.log"
    patch_legacy_mode(root)
    step5_migration.apply(root, log)
    commit_stage(
        root,
        "fix(migration): make legacy resume lossless and actionable",
        ["src/render.ts", "src/store.ts", "src/routing.ts", "runtime", "tests-ts/legacy-resume-hardening.test.mjs"],
        ["byte-for-byte legacy backup", "validate to next continuation", "explicit discovery migration", "semantic PASS preservation"],
        log,
        commits,
        summary,
    )

    log = logs / "06-installer.log"
    patch_installer_template()
    step6_installer.apply(root, log)
    commit_stage(
        root,
        "fix(installer): support immutable remote installs and guarded retirement",
        ["opencode-agents.py", "README.md", "tests/test_installer_regression.py"],
        ["mocked GitHub commit/tree/blob install", "top-level runtime JS and declarations", "guarded retirement backup", "customized-file preservation"],
        log,
        commits,
        summary,
    )

    log = logs / "07-build.log"
    step7_runtime.apply(root, log)
    patch_release_gate_fixture(root)
    step7_fixups.apply(root)
    step7_build.apply(root, log)
    ensure_gitignore(root)
    clean_generated_noise(root, remove_dist_tools=True)
    common.npm_exec(root, ["ci"], log=log)
    common.npm_exec(root, ["run", "check:generated"], log=log)
    common.npm_exec(root, ["test"], log=log)
    common.npm_exec(root, ["run", "typecheck"], log=log)
    common.npm_exec(root, ["run", "check:generated"], log=log)
    common.run(["git", "diff", "--exit-code", "--", "runtime"], cwd=root, log=log)
    clean_generated_noise(root, remove_dist_tools=True)
    sha7 = commit_stage(
        root,
        "build: make TypeScript runtime reproducible and add cross-platform CI",
        [
            "src", "runtime", "tools", "tests-ts", "tests", "scripts", ".github/workflows",
            ".npmrc", ".gitignore", "package.json", "package-lock.json", "tsconfig.json",
            "tsconfig.tools.json", "types", "opencode-agents.py",
        ],
        ["npm ci", "npm test", "real plugin API typecheck", "generated runtime drift", "actual native tool invocation", "journey/symlink/journal/recovery baseline"],
        log,
        commits,
        summary,
    )

    common.assert_clean(root)
    result = {
        "schema_version": 1,
        "target_branch": common.TARGET_BRANCH,
        "base_commit": BASE_COMMIT,
        "python_snapshot": PYTHON_SNAPSHOT,
        "commits": commits,
        "sha7": sha7,
        "automation_source": common.run(["git", "rev-parse", "HEAD"], cwd=automation_root).stdout.strip(),
    }
    (result_dir / "prepare.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"sha7={sha7}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
