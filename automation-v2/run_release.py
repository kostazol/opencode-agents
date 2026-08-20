from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

from bootstrap import CHECKS, EXPECTED_MESSAGES, chain_metadata, clean, common, history, report, sha_at, sync_target, write_json, write_output

import step9_release


def fresh_install_status_update(root: Path, log: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="opencode-agents-install-gate-") as temporary:
        base = Path(temporary)
        target = base / "target"
        backup = base / "backup"
        common.run([sys.executable, "opencode-agents.py", "install", "--source", str(root), "--target", str(target)], cwd=root, log=log)
        common.run([sys.executable, "opencode-agents.py", "status", "--target", str(target)], cwd=root, log=log)
        common.run(
            [sys.executable, "opencode-agents.py", "update", "--source", str(root), "--target", str(target), "--backup", str(backup)],
            cwd=root,
            log=log,
        )
        common.run([sys.executable, "opencode-agents.py", "status", "--target", str(target)], cwd=root, log=log)
        manifest = json.loads((target / ".opencode-agents-manifest.json").read_text(encoding="utf-8"))
        paths = {item["path"] for item in manifest["files"]}
        if not {"runtime/orchestrator.js", "runtime/orchestrator.d.ts"}.issubset(paths):
            raise RuntimeError("fresh installer manifest omitted top-level runtime JS/declaration files")
        if not (backup / "runtime/orchestrator.js").is_file():
            raise RuntimeError("update gate did not create the mandatory runtime backup")


def full_gates(root: Path, log: Path) -> None:
    common.npm_exec(root, ["ci"], log=log)
    common.npm_exec(root, ["run", "check:generated"], log=log)
    common.npm_exec(root, ["test"], log=log)
    common.npm_exec(root, ["run", "typecheck"], log=log)
    common.npm_exec(root, ["run", "check:generated"], log=log)
    common.run(["git", "diff", "--exit-code", "--", "runtime", "package.json", "package-lock.json"], cwd=root, log=log)
    fresh_install_status_update(root, log)
    clean(root)


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: run_release.py <automation-checkout> <target-checkout> <docs-json> <result-dir>")
    automation_root = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    docs_path = Path(sys.argv[3]).resolve()
    result_dir = Path(sys.argv[4]).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    log = result_dir / "09-release.log"
    summary = Path(os.environ["GITHUB_STEP_SUMMARY"]) if os.environ.get("GITHUB_STEP_SUMMARY") else None
    docs = json.loads(docs_path.read_text(encoding="utf-8"))

    sync_target(root)
    sha8 = sha_at(root, 8)
    if not sha8 or sha8 != docs["sha8"] or len(history(root)) < 7:
        raise RuntimeError(f"release runner requires exact commit 8: discovered={sha8}, expected={docs['sha8']}")

    sha9 = sha_at(root, 9)
    matrix_candidate = {
        "status": "passed",
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "url": f"https://github.com/{common.REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
        "commit": sha8,
        "platforms": ["ubuntu-latest", "windows-latest", "macos-latest"],
        "node": [20, 22],
    }

    if sha9:
        report(summary, chain_metadata(root)[8], reused=True)
    else:
        if common.run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip() != sha8:
            raise RuntimeError("target is ahead of commit 8 without the required release commit")
        full_gates(root, log)
        required = [item["sha"] for item in chain_metadata(root)[:8]]
        metadata = {
            "required_commits": required,
            "code_ref": docs["sha7"],
            "docs_ref": sha8,
            "matrix": [docs["matrix_code"], matrix_candidate],
        }
        metadata_path = result_dir / "release-input.json"
        write_json(metadata_path, metadata)
        step9_release.apply(root, log, metadata_path)
        full_gates(root, log)
        sha9 = common.commit_and_push(
            root,
            EXPECTED_MESSAGES[7],
            ["VERSION", "RELEASE.md", "ROADMAP.md", "release/6.0.1-gates.json", "tests/test_release_metadata.py"],
            log=log,
        )
        report(summary, {"message": EXPECTED_MESSAGES[7], "sha": sha9, "checks": CHECKS[EXPECTED_MESSAGES[7]]})

    sync_target(root)
    exact_sha9 = sha_at(root, 9)
    if not exact_sha9 or exact_sha9 != sha9:
        raise RuntimeError(f"release commit remote mismatch: local={sha9}, remote-chain={exact_sha9}")
    result = {
        "schema_version": 2,
        "target_branch": common.TARGET_BRANCH,
        "commits": chain_metadata(root)[:9],
        "sha7": docs["sha7"],
        "sha8": sha8,
        "sha9": exact_sha9,
        "matrix_code": docs["matrix_code"],
        "matrix_candidate": matrix_candidate,
        "local_release_gates": "passed" if len(history(root)) == 8 else "reused-existing-release",
        "environment_blocked": [],
        "automation_source": common.run(["git", "rev-parse", "HEAD"], cwd=automation_root).stdout.strip(),
    }
    write_json(result_dir / "release.json", result)
    write_output("sha9", exact_sha9)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
