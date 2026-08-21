from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from final_common import MESSAGES, assert_expected_head, clean, commit_stage, common, configure, history, matrix_evidence, write_json, write_output
import step9_release


def fresh_install_status_update(root: Path, log: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="opencode-agents-final-install-") as temporary:
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
        required = {"runtime/orchestrator.js", "runtime/orchestrator.d.ts"}
        if not required.issubset(paths):
            raise RuntimeError(f"installer manifest omitted final top-level runtime files: {required - paths}")
        if not (backup / "runtime/orchestrator.js").is_file():
            raise RuntimeError("update did not create the mandatory runtime backup")


def full_gates(root: Path, log: Path) -> None:
    common.npm_exec(root, ["ci"], log=log)
    common.npm_exec(root, ["run", "check:generated"], log=log)
    common.npm_exec(root, ["test"], log=log)
    common.npm_exec(root, ["run", "typecheck"], log=log)
    common.npm_exec(root, ["run", "check:generated"], log=log)
    common.run(["git", "diff", "--exit-code", "--", "runtime", "package.json", "package-lock.json"], cwd=root, log=log)
    fresh_install_status_update(root, log)
    clean(root)


def align_release_text(root: Path) -> None:
    for relative in ["RELEASE.md", "ROADMAP.md"]:
        candidate = root / relative
        content = candidate.read_text(encoding="utf-8")
        content = (
            content
            .replace("Node 20 and 22", "Node 22 and 24")
            .replace("Node 20/22", "Node 22/24")
            .replace("Node 20, 22", "Node 22, 24")
        )
        candidate.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: run_release_from_main.py <target-checkout> <docs-json> <result-dir>")
    root = Path(sys.argv[1]).resolve()
    docs_path = Path(sys.argv[2]).resolve()
    result_dir = Path(sys.argv[3]).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    log = result_dir / "09-release.log"
    docs = json.loads(docs_path.read_text(encoding="utf-8"))
    sha_docs = docs["sha_docs"]

    configure(root)
    assert_expected_head(root, sha_docs)
    commits = history(root)
    if len(commits) != 8:
        raise RuntimeError(f"release stage requires exactly eight branch commits before release, got {commits}")

    full_gates(root, log)
    matrix_candidate = matrix_evidence(sha_docs, "release-candidate")
    required_commits = [item["sha"] for item in commits]
    metadata = {
        "required_commits": required_commits,
        "code_ref": docs["sha_build"],
        "docs_ref": sha_docs,
        "matrix": [docs["matrix_code"], matrix_candidate],
    }
    metadata_path = result_dir / "release-input.json"
    write_json(metadata_path, metadata)
    step9_release.apply(root, log, metadata_path)
    align_release_text(root)
    full_gates(root, log)

    sha_release = commit_stage(
        root,
        MESSAGES[8],
        ["VERSION", "RELEASE.md", "ROADMAP.md", "release/6.0.1-gates.json", "tests/test_release_metadata.py"],
        log,
    )
    result = {
        "schema_version": 1,
        "commits": history(root)[:9],
        "sha_build": docs["sha_build"],
        "sha_docs": sha_docs,
        "sha_release": sha_release,
        "matrix_code": docs["matrix_code"],
        "matrix_candidate": matrix_candidate,
        "local_release_gates": "passed",
    }
    write_json(result_dir / "release.json", result)
    write_output("sha_release", sha_release)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
