from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for candidate in [
    ROOT / "automation",
    ROOT / "automation-v2",
    ROOT / "automation-v3",
    ROOT / "automation-v4",
    ROOT / "automation-v5",
]:
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("hardening_prepare_v5", ROOT / "automation-v5" / "run_prepare.py")
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load the final workbench preparation module")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
prepare = module.prepare
common = prepare.common

REPOSITORY = "kostazol/opencode-agents"
TARGET_BRANCH = "agent/6.0.1-final-complete"
BASE_SHA = "5c897d5b3afba74940fcd188d2a2e13b21ebcc0b"
BASELINE_TEST_SHA = "6a8baa4b70d6157e28661a8bae17b8c4b93ef779"

MESSAGES = [
    "fix(controller): enforce artifact contracts and stale-input protection",
    "fix(routing): pass correction sources and enforce legal state invariants",
    "fix(protocol): strengthen NFR applicability and traceability",
    "fix(migration): make legacy resume lossless and actionable",
    "fix(installer): support immutable remote installs and guarded retirement",
    "build: make TypeScript runtime reproducible and add cross-platform CI",
    "fix(build): align Node support with current OpenCode SDK",
    "docs: align roadmap and release claims with executable gates",
    "release: finalize stable 6.0.1",
]

common.TARGET_BRANCH = TARGET_BRANCH


def configure(root: Path) -> None:
    common.run(["git", "config", "user.name", "OpenCode Agents Finalization Bot"], cwd=root)
    common.run(["git", "config", "user.email", "opencode-agents-finalization@users.noreply.github.com"], cwd=root)
    common.run(["git", "fetch", "origin", TARGET_BRANCH, "main", "--tags", "--force"], cwd=root)


def clean(root: Path) -> None:
    prepare.clean(root)
    for candidate in root.rglob("__pycache__"):
        if candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)
    for candidate in root.rglob("*.pyc"):
        candidate.unlink(missing_ok=True)


def history(root: Path) -> list[dict[str, str]]:
    if common.run(["git", "merge-base", "--is-ancestor", BASE_SHA, "HEAD"], cwd=root, check=False).returncode != 0:
        raise RuntimeError(f"target branch is not descended from the audited main base {BASE_SHA}")
    shas = common.run(["git", "rev-list", "--reverse", f"{BASE_SHA}..HEAD"], cwd=root).stdout.splitlines()
    if len(shas) > len(MESSAGES):
        raise RuntimeError(f"target branch contains unexpected extra commits: {shas}")
    result: list[dict[str, str]] = []
    previous = BASE_SHA
    for index, sha in enumerate(shas):
        parent = common.run(["git", "rev-parse", f"{sha}^"], cwd=root).stdout.strip()
        message = common.run(["git", "show", "-s", "--format=%s", sha], cwd=root).stdout.strip()
        if parent != previous:
            raise RuntimeError(f"non-linear finalization history at {sha}: expected parent {previous}, got {parent}")
        if message != MESSAGES[index]:
            raise RuntimeError(f"unexpected commit {index + 1}: expected {MESSAGES[index]!r}, got {message!r}")
        result.append({"sha": sha, "message": message})
        previous = sha
    return result


def assert_expected_head(root: Path, expected: str) -> None:
    actual = common.run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    remote = common.run(["git", "ls-remote", "origin", f"refs/heads/{TARGET_BRANCH}"], cwd=root).stdout.split()[0]
    if actual != expected or remote != expected:
        raise RuntimeError(f"target head mismatch: local={actual}, remote={remote}, expected={expected}")
    common.assert_clean(root)


def commit_stage(root: Path, message: str, allowed: list[str], log: Path) -> str:
    clean(root)
    sha = common.commit_and_push(root, message, allowed, log=log)
    print(f"PUBLISHED {sha} {message}")
    return sha


def write_json(candidate: Path, value: object) -> None:
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"{name}={value}\n")


def matrix_evidence(commit: str, phase: str) -> dict[str, Any]:
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    return {
        "phase": phase,
        "status": "passed",
        "commit": commit,
        "run_id": run_id,
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
        "platforms": ["ubuntu-latest", "windows-latest", "macos-latest"],
        "node": [22, 24],
    }
