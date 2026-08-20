from __future__ import annotations

import os
from pathlib import Path
import sys

from bootstrap import CHECKS, EXPECTED_MESSAGES, chain_metadata, clean, common, history, report, sha_at, sync_target, write_json, write_output

import step8_docs_v2


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: run_docs.py <automation-checkout> <target-checkout> <prepare-json> <result-dir>")
    automation_root = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    prepare_path = Path(sys.argv[3]).resolve()
    result_dir = Path(sys.argv[4]).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    log = result_dir / "08-docs.log"
    summary = Path(os.environ["GITHUB_STEP_SUMMARY"]) if os.environ.get("GITHUB_STEP_SUMMARY") else None

    prepare = __import__("json").loads(prepare_path.read_text(encoding="utf-8"))
    sync_target(root)
    items = history(root)
    sha7 = sha_at(root, 7)
    if not sha7 or sha7 != prepare["sha7"] or len(items) < 6:
        raise RuntimeError(f"documentation runner requires exact commit 7: discovered={sha7}, expected={prepare['sha7']}")

    sha8 = sha_at(root, 8)
    if sha8:
        existing = chain_metadata(root)[7]
        report(summary, existing, reused=True)
    else:
        if common.run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip() != sha7:
            raise RuntimeError("target is ahead of commit 7 without the required documentation commit")
        step8_docs_v2.apply(root, log, sha7)
        common.npm_exec(root, ["ci"], log=log)
        common.npm_exec(root, ["test"], log=log)
        common.npm_exec(root, ["run", "typecheck"], log=log)
        common.npm_exec(root, ["run", "check:generated"], log=log)
        common.run(["git", "diff", "--exit-code", "--", "runtime", "package.json", "package-lock.json"], cwd=root, log=log)
        clean(root)
        sha8 = common.commit_and_push(
            root,
            EXPECTED_MESSAGES[6],
            ["README.md", "ROADMAP.md", "docs/RELEASE_GATES.md", "tests/test_docs_release.py"],
            log=log,
        )
        report(summary, {"message": EXPECTED_MESSAGES[6], "sha": sha8, "checks": CHECKS[EXPECTED_MESSAGES[6]]})

    sync_target(root)
    exact_sha8 = sha_at(root, 8)
    if not exact_sha8 or exact_sha8 != sha8:
        raise RuntimeError(f"documentation commit remote mismatch: local={sha8}, remote-chain={exact_sha8}")
    matrix_code = {
        "status": "passed",
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "url": f"https://github.com/{common.REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
        "commit": sha7,
        "platforms": ["ubuntu-latest", "windows-latest", "macos-latest"],
        "node": [20, 22],
    }
    result = {
        "schema_version": 2,
        "target_branch": common.TARGET_BRANCH,
        "commits": chain_metadata(root)[:8],
        "sha7": sha7,
        "sha8": exact_sha8,
        "matrix_code": matrix_code,
        "automation_source": common.run(["git", "rev-parse", "HEAD"], cwd=automation_root).stdout.strip(),
    }
    write_json(result_dir / "docs.json", result)
    write_output("sha8", exact_sha8)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
