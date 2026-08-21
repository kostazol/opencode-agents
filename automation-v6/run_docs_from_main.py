from __future__ import annotations

import json
from pathlib import Path
import sys

from final_common import MESSAGES, assert_expected_head, clean, commit_stage, common, configure, history, matrix_evidence, write_json, write_output
import step8_docs_v2


step8_docs_v2.GATES_DOC = (
    step8_docs_v2.GATES_DOC
    .replace("Node 20 and 22", "Node 22 and 24")
    .replace("Node 20, 22", "Node 22, 24")
)


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: run_docs_from_main.py <target-checkout> <prepare-json> <result-dir>")
    root = Path(sys.argv[1]).resolve()
    prepare_path = Path(sys.argv[2]).resolve()
    result_dir = Path(sys.argv[3]).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    log = result_dir / "08-docs.log"
    prepared = json.loads(prepare_path.read_text(encoding="utf-8"))
    sha_build = prepared["sha_build"]

    configure(root)
    assert_expected_head(root, sha_build)
    commits = history(root)
    if len(commits) != 7:
        raise RuntimeError(f"documentation stage requires exactly seven implementation commits, got {commits}")

    step8_docs_v2.apply(root, log, sha_build)
    common.npm_exec(root, ["ci"], log=log)
    common.npm_exec(root, ["test"], log=log)
    common.npm_exec(root, ["run", "typecheck"], log=log)
    common.npm_exec(root, ["run", "check:generated"], log=log)
    common.run(["git", "diff", "--exit-code", "--", "runtime", "package.json", "package-lock.json"], cwd=root, log=log)
    clean(root)

    sha_docs = commit_stage(
        root,
        MESSAGES[7],
        ["README.md", "ROADMAP.md", "docs/RELEASE_GATES.md", "tests/test_docs_release.py"],
        log,
    )
    result = {
        "schema_version": 1,
        "commits": history(root)[:8],
        "sha_build": sha_build,
        "sha_docs": sha_docs,
        "matrix_code": matrix_evidence(sha_build, "implementation"),
    }
    write_json(result_dir / "docs.json", result)
    write_output("sha_docs", sha_docs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
