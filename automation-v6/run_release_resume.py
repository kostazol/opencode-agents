from __future__ import annotations

import json
from pathlib import Path
import sys

from final_common import configure, history, matrix_evidence, write_json
import run_release_from_main


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: run_release_resume.py <target-checkout> <result-dir>")
    root = Path(sys.argv[1]).resolve()
    result_dir = Path(sys.argv[2]).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)

    configure(root)
    commits = history(root)
    if len(commits) != 8:
        raise RuntimeError(f"release resume requires the eight verified pre-release commits, got {commits}")
    sha_build = commits[6]["sha"]
    sha_docs = commits[7]["sha"]
    docs = {
        "schema_version": 1,
        "commits": commits,
        "sha_build": sha_build,
        "sha_docs": sha_docs,
        "matrix_code": {
            **matrix_evidence(sha_build, "implementation"),
            "run_id": "32445239800",
            "url": "https://github.com/kostazol/opencode-agents/actions/runs/32445239800",
        },
    }
    docs_path = result_dir / "docs-resume.json"
    write_json(docs_path, docs)
    sys.argv = ["run_release_from_main.py", str(root), str(docs_path), str(result_dir)]
    return run_release_from_main.main()


if __name__ == "__main__":
    raise SystemExit(main())
