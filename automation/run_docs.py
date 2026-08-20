from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

import common
import step8_docs_v2


MESSAGE = "docs: align roadmap and release claims with executable gates"


def clean(root: Path) -> None:
    shutil.rmtree(root / "dist-tools", ignore_errors=True)
    for candidate in root.rglob("__pycache__"):
        if candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)
    for candidate in root.rglob("*.pyc"):
        candidate.unlink(missing_ok=True)


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: run_docs.py <automation-checkout> <target-checkout> <prepare-json> <result-dir>")
    automation_root = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    prepare_path = Path(sys.argv[3]).resolve()
    result_dir = Path(sys.argv[4]).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    log = result_dir / "08-docs.log"
    prepare = json.loads(prepare_path.read_text(encoding="utf-8"))
    sha7 = prepare["sha7"]

    common.run(["git", "config", "user.name", "OpenCode Agents Release Bot"], cwd=root)
    common.run(["git", "config", "user.email", "opencode-agents-release@users.noreply.github.com"], cwd=root)
    common.run(["git", "fetch", "origin", common.TARGET_BRANCH, "--force"], cwd=root)
    head = common.run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    remote = common.run(["git", "ls-remote", "origin", f"refs/heads/{common.TARGET_BRANCH}"], cwd=root).stdout.split()[0]
    if head != sha7 or remote != sha7:
        raise RuntimeError(f"documentation stage must start at commit 7: local={head}, remote={remote}, expected={sha7}")
    common.assert_clean(root)

    step8_docs_v2.apply(root, log, sha7)
    common.npm_exec(root, ["ci"], log=log)
    common.npm_exec(root, ["test"], log=log)
    common.npm_exec(root, ["run", "typecheck"], log=log)
    common.npm_exec(root, ["run", "check:generated"], log=log)
    common.run(["git", "diff", "--exit-code", "--", "runtime", "package.json", "package-lock.json"], cwd=root, log=log)
    clean(root)

    sha8 = common.commit_and_push(
        root,
        MESSAGE,
        ["README.md", "ROADMAP.md", "docs/RELEASE_GATES.md", "tests/test_docs_release.py"],
        log=log,
    )
    common.assert_clean(root)

    commits = list(prepare["commits"])
    item = {
        "message": MESSAGE,
        "sha": sha8,
        "checks": ["immutable README ref", "executable release-gate documentation", "npm test", "plugin API typecheck", "generated drift"],
    }
    commits.append(item)
    line = f"- `{sha8}` — {MESSAGE} — {', '.join(item['checks'])}\n"
    print(line, end="")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)

    result = {
        "schema_version": 1,
        "target_branch": common.TARGET_BRANCH,
        "commits": commits,
        "sha7": sha7,
        "sha8": sha8,
        "automation_source": common.run(["git", "rev-parse", "HEAD"], cwd=automation_root).stdout.strip(),
        "matrix_code": {
            "status": "passed",
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "url": f"https://github.com/{common.REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
            "commit": sha7,
            "platforms": ["ubuntu-latest", "windows-latest", "macos-latest"],
            "node": [20, 22],
        },
    }
    (result_dir / "docs.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"sha8={sha8}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
