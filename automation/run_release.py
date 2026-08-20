from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import common
import step9_release


MESSAGE = "release: finalize stable 6.0.1"


def clean(root: Path) -> None:
    shutil.rmtree(root / "dist-tools", ignore_errors=True)
    for candidate in root.rglob("__pycache__"):
        if candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)
    for candidate in root.rglob("*.pyc"):
        candidate.unlink(missing_ok=True)


def fresh_install_status_update(root: Path, log: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="opencode-agents-install-gate-") as temporary:
        base = Path(temporary)
        target = base / "target"
        backup = base / "backup"
        python = sys.executable
        common.run(
            [python, "opencode-agents.py", "install", "--source", str(root), "--target", str(target)],
            cwd=root,
            log=log,
        )
        common.run([python, "opencode-agents.py", "status", "--target", str(target)], cwd=root, log=log)
        common.run(
            [
                python,
                "opencode-agents.py",
                "update",
                "--source",
                str(root),
                "--target",
                str(target),
                "--backup",
                str(backup),
            ],
            cwd=root,
            log=log,
        )
        common.run([python, "opencode-agents.py", "status", "--target", str(target)], cwd=root, log=log)
        manifest = json.loads((target / ".opencode-agents-manifest.json").read_text(encoding="utf-8"))
        paths = {item["path"] for item in manifest["files"]}
        if "runtime/orchestrator.js" not in paths or "runtime/orchestrator.d.ts" not in paths:
            raise RuntimeError("fresh installer manifest omitted top-level runtime JS/declaration files")
        if not (backup / "runtime/orchestrator.js").is_file():
            raise RuntimeError("update gate did not create the mandatory runtime backup")


def full_local_gates(root: Path, log: Path) -> None:
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
    docs = json.loads(docs_path.read_text(encoding="utf-8"))
    sha8 = docs["sha8"]

    common.run(["git", "config", "user.name", "OpenCode Agents Release Bot"], cwd=root)
    common.run(["git", "config", "user.email", "opencode-agents-release@users.noreply.github.com"], cwd=root)
    common.run(["git", "fetch", "origin", common.TARGET_BRANCH, "--force"], cwd=root)
    head = common.run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    remote = common.run(["git", "ls-remote", "origin", f"refs/heads/{common.TARGET_BRANCH}"], cwd=root).stdout.split()[0]
    if head != sha8 or remote != sha8:
        raise RuntimeError(f"release stage must start at commit 8: local={head}, remote={remote}, expected={sha8}")
    common.assert_clean(root)

    # Candidate commit has already passed the six-way matrix through the workflow dependency.
    full_local_gates(root, log)

    required_commits = [item["sha"] for item in docs["commits"]]
    if len(required_commits) != 8:
        raise RuntimeError(f"release requires exactly the first eight commits, got {required_commits}")
    matrix_candidate = {
        "status": "passed",
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "url": f"https://github.com/{common.REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
        "commit": sha8,
        "platforms": ["ubuntu-latest", "windows-latest", "macos-latest"],
        "node": [20, 22],
    }
    metadata = {
        "required_commits": required_commits,
        "code_ref": docs["sha7"],
        "docs_ref": sha8,
        "matrix": [docs["matrix_code"], matrix_candidate],
    }
    metadata_path = result_dir / "release-input.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    step9_release.apply(root, log, metadata_path)
    full_local_gates(root, log)
    sha9 = common.commit_and_push(
        root,
        MESSAGE,
        ["VERSION", "RELEASE.md", "ROADMAP.md", "release/6.0.1-gates.json", "tests/test_release_metadata.py"],
        log=log,
    )
    common.assert_clean(root)

    commits = list(docs["commits"])
    item = {
        "message": MESSAGE,
        "sha": sha9,
        "checks": [
            "candidate Linux/Windows/macOS Node 20/22 matrix",
            "npm ci and npm test",
            "actual plugin API typecheck",
            "generated runtime drift",
            "fresh install/status/update",
            "all executable release metadata gates",
        ],
    }
    commits.append(item)
    line = f"- `{sha9}` — {MESSAGE} — {', '.join(item['checks'])}\n"
    print(line, end="")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)

    result = {
        "schema_version": 1,
        "target_branch": common.TARGET_BRANCH,
        "commits": commits,
        "sha7": docs["sha7"],
        "sha8": sha8,
        "sha9": sha9,
        "matrix_code": docs["matrix_code"],
        "matrix_candidate": matrix_candidate,
        "local_release_gates": "passed",
        "environment_blocked": [],
        "automation_source": common.run(["git", "rev-parse", "HEAD"], cwd=automation_root).stdout.strip(),
    }
    (result_dir / "release.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"sha9={sha9}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
