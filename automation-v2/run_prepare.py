from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

from bootstrap import AUTOMATION, CHECKS, COMMIT_ONE, EXPECTED_MESSAGES, chain_metadata, clean, common, history, report, sha_at, sync_target, write_json, write_output

import step2_controller
import step3_routing
import step4_protocol
import step5_migration
import step6_installer
import step7_build
import step7_fixups
import step7_runtime


def ensure_gitignore(root: Path) -> None:
    candidate = root / ".gitignore"
    lines = (candidate.read_text(encoding="utf-8") if candidate.exists() else "").replace("\r\n", "\n").splitlines()
    for item in ["node_modules/", "dist-tools/", "__pycache__/", "*.pyc"]:
        if item not in lines:
            lines.append(item)
    candidate.write_text("\n".join(lines).strip("\n") + "\n", encoding="utf-8", newline="\n")


def patch_legacy_mode(root: Path) -> None:
    candidate = root / "src/routing.ts"
    source = candidate.read_text(encoding="utf-8")
    old = 'mode: correction ? "CORRECTION" : next.analysis_revision === 1 ? "INITIAL" : next.legacy_migrated ? "LEGACY_MIGRATION" : "FOLLOW_UP",'
    new = 'mode: correction ? "CORRECTION" : next.legacy_migrated ? "LEGACY_MIGRATION" : next.analysis_revision === 1 ? "INITIAL" : "FOLLOW_UP",'
    if old in source:
        candidate.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")
    elif new not in source:
        raise RuntimeError("legacy migration mode expression is neither old nor hardened")


def patch_installer_template() -> None:
    template = step6_installer.INSTALLER.replace("from dataclasses import dataclass\n", "")
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
    if old in template:
        template = template.replace(old, new, 1)
    elif "class FileRecord:" not in template or "self.sha256 = sha256" not in template:
        raise RuntimeError("installer FileRecord template is not recognized")
    step6_installer.INSTALLER = template


def enhanced_historical_manifests(root: Path) -> dict[str, set[str]]:
    refs = ["0570ed9521c67eb21669479805f4c7bfdd1db743", "7b43e411bc87da8182fa1c0c7a972b005831a573"]
    candidates: set[str] = {"runtime/orchestrator.py"}
    for ref in refs:
        paths = common.run(["git", "ls-tree", "-r", "--name-only", ref], cwd=root).stdout.splitlines()
        for relative in paths:
            normalized = relative.replace("\\", "/")
            parts = normalized.split("/")
            filename = parts[-1].lower()
            if normalized.startswith("runtime/orchestrator_core/"):
                candidates.add(normalized)
            elif "orchestrator" in filename and any("plugin" in part.lower() for part in parts[:-1]):
                candidates.add(normalized)
    result: dict[str, set[str]] = {}
    for relative in sorted(candidates):
        for ref in refs:
            process = subprocess.run(["git", "show", f"{ref}:{relative}"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if process.returncode == 0:
                result.setdefault(relative, set()).add(hashlib.sha256(process.stdout).hexdigest())
    return result


def patch_build_templates() -> None:
    if '"esModuleInterop": true' not in step7_build.TSCONFIG:
        step7_build.TSCONFIG = step7_build.TSCONFIG.replace(
            '    "strict": true,',
            '    "strict": true,\n    "esModuleInterop": true,',
            1,
        )
    step7_build.CHECK_GENERATED = r'''
import { mkdtemp, readdir, readFile, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { spawnSync } from "node:child_process"

async function files(root) {
  const result = new Map()
  async function walk(directory) {
    let entries = []
    try { entries = await readdir(directory, { withFileTypes: true }) } catch (error) { if (error.code === "ENOENT") return; throw error }
    for (const entry of entries) {
      const candidate = path.join(directory, entry.name)
      if (entry.isDirectory()) await walk(candidate)
      else if (entry.name.endsWith(".js") || entry.name.endsWith(".d.ts")) result.set(path.relative(root, candidate).replaceAll(path.sep, "/"), await readFile(candidate))
    }
  }
  await walk(root)
  return result
}

const temporary = await mkdtemp(path.join(os.tmpdir(), "opencode-agents-generated-"))
try {
  const out = path.join(temporary, "runtime")
  const tsc = path.join("node_modules", "typescript", "bin", "tsc")
  const compiled = spawnSync(process.execPath, [tsc, "-p", "tsconfig.json", "--outDir", out, "--declarationDir", out], { stdio: "inherit" })
  if (compiled.status !== 0) process.exit(compiled.status ?? 1)
  const expected = await files(out)
  const actual = await files("runtime")
  const names = [...new Set([...expected.keys(), ...actual.keys()])].sort()
  const drift = names.filter((name) => !expected.has(name) || !actual.has(name) || !expected.get(name).equals(actual.get(name)))
  if (drift.length) {
    console.error("generated runtime drift:")
    for (const name of drift) console.error(`- ${name}`)
    process.exit(1)
  }
  console.log(`generated runtime matches ${expected.size} compiled files`)
} finally {
  await rm(temporary, { recursive: true, force: true })
}
'''


def patch_final_sources(root: Path) -> None:
    fixture = root / "tests-ts/release-gates.test.mjs"
    source = fixture.read_text(encoding="utf-8")
    old = '''  const conflictTarget = structuredClone(target)
  conflictTarget.state_revision = 3
'''
    new = '''  const conflictTarget = structuredClone(target)
  conflictTarget.state_revision = 3
  conflictTarget.pending.issued_state_revision = 3
'''
    if old in source:
        fixture.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")
    elif "conflictTarget.pending.issued_state_revision = 3" not in source:
        raise RuntimeError("transaction conflict fixture is not recognized")

    store = root / "src/store.ts"
    store_source = store.read_text(encoding="utf-8")
    old_store = '''      if (!state.pending) {
        if (state.applied[event.transition_id]) return applyEvent(this.base, state, event, analysis, expectedStateRevision)
        throw new ProtocolError("state.pending", "event cannot be applied without a pending transition")
      }
'''
    new_store = '''      if (!state.pending) {
        if (state.applied[event.transition_id]) return applyEvent(this.base, state, event, analysis, undefined)
        throw new ProtocolError("state.pending", "event cannot be applied without a pending transition")
      }
'''
    if old_store in store_source:
        store_source = store_source.replace(old_store, new_store, 1)
    elif new_store not in store_source:
        raise RuntimeError("idempotent journal replay block is not recognized")
    store.write_text(store_source, encoding="utf-8", newline="\n")


def commit(root: Path, message: str, allowed: list[str], checks: list[str], log: Path, summary: Path | None) -> str:
    clean(root)
    sha = common.commit_and_push(root, message, allowed, log=log)
    report(summary, {"message": message, "sha": sha, "checks": checks})
    return sha


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: run_prepare.py <automation-checkout> <target-checkout> <result-dir>")
    automation_root = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    result_dir = Path(sys.argv[3]).resolve()
    logs = result_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    summary = Path(os.environ["GITHUB_STEP_SUMMARY"]) if os.environ.get("GITHUB_STEP_SUMMARY") else None

    sync_target(root)
    existing = history(root)
    for item in chain_metadata(root):
        report(summary, item, reused=item["sha"] != COMMIT_ONE)

    if len(existing) < 1:
        baseline = logs / "01-red-baseline.log"
        common.expect_failure(["node", "--test", "tests-ts/release-blockers.test.mjs"], cwd=root, log=baseline)
        common.expect_failure([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_installer_hardening.py", "-v"], cwd=root, log=baseline)
        log = logs / "02-controller.log"
        step2_controller.apply(root, log)
        commit(root, EXPECTED_MESSAGES[0], ["src", "runtime", "types", "tests-ts/controller-hardening.test.mjs"], CHECKS[EXPECTED_MESSAGES[0]], log, summary)

    if len(history(root)) < 2:
        log = logs / "03-routing.log"
        step3_routing.apply(root, log)
        commit(root, EXPECTED_MESSAGES[1], ["src/routing.ts", "src/state.ts", "runtime", "tests-ts/routing-state-hardening.test.mjs"], CHECKS[EXPECTED_MESSAGES[1]], log, summary)

    if len(history(root)) < 3:
        log = logs / "04-protocol.log"
        step4_protocol.apply(root, log)
        commit(root, EXPECTED_MESSAGES[2], ["src/analysis.ts", "runtime", "tests-ts/nfr-adversarial.test.mjs"], CHECKS[EXPECTED_MESSAGES[2]], log, summary)

    if len(history(root)) < 4:
        log = logs / "05-migration.log"
        patch_legacy_mode(root)
        step5_migration.apply(root, log)
        commit(root, EXPECTED_MESSAGES[3], ["src/render.ts", "src/store.ts", "src/routing.ts", "runtime", "tests-ts/legacy-resume-hardening.test.mjs"], CHECKS[EXPECTED_MESSAGES[3]], log, summary)

    if len(history(root)) < 5:
        log = logs / "06-installer.log"
        patch_installer_template()
        step6_installer.historical_manifests = enhanced_historical_manifests
        step6_installer.apply(root, log)
        commit(root, EXPECTED_MESSAGES[4], ["opencode-agents.py", "README.md", "tests/test_installer_regression.py"], CHECKS[EXPECTED_MESSAGES[4]], log, summary)

    if len(history(root)) < 6:
        log = logs / "07-build.log"
        patch_build_templates()
        step7_runtime.apply(root, log)
        step7_fixups.apply(root)
        patch_final_sources(root)
        step7_build.apply(root, log)
        ensure_gitignore(root)
        clean(root)
        common.npm_exec(root, ["ci"], log=log)
        common.npm_exec(root, ["run", "check:generated"], log=log)
        common.npm_exec(root, ["test"], log=log)
        common.npm_exec(root, ["run", "typecheck"], log=log)
        common.npm_exec(root, ["run", "check:generated"], log=log)
        common.run(["git", "diff", "--exit-code", "--", "runtime", "package.json", "package-lock.json"], cwd=root, log=log)
        clean(root)
        commit(
            root,
            EXPECTED_MESSAGES[5],
            ["src", "runtime", "tools", "tests-ts", "tests", "scripts", ".github/workflows", ".npmrc", ".gitignore", "package.json", "package-lock.json", "tsconfig.json", "tsconfig.tools.json", "types", "opencode-agents.py"],
            CHECKS[EXPECTED_MESSAGES[5]],
            log,
            summary,
        )

    sync_target(root)
    sha7 = sha_at(root, 7)
    if not sha7:
        raise RuntimeError("prepare did not produce or discover commit 7")
    result = {
        "schema_version": 2,
        "target_branch": common.TARGET_BRANCH,
        "commits": chain_metadata(root)[:7],
        "sha7": sha7,
        "automation_source": common.run(["git", "rev-parse", "HEAD"], cwd=automation_root).stdout.strip(),
    }
    write_json(result_dir / "prepare.json", result)
    write_output("sha7", sha7)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
