from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

AUTOMATION = Path(__file__).resolve().parents[1] / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

import common  # noqa: E402

BASE_COMMIT = "7b43e411bc87da8182fa1c0c7a972b005831a573"
PYTHON_SNAPSHOT = "0570ed9521c67eb21669479805f4c7bfdd1db743"
COMMIT_ONE = common.BASELINE_SHA
EXPECTED_MESSAGES = [
    "fix(controller): enforce artifact contracts and stale-input protection",
    "fix(routing): pass correction sources and enforce legal state invariants",
    "fix(protocol): strengthen NFR applicability and traceability",
    "fix(migration): make legacy resume lossless and actionable",
    "fix(installer): support immutable remote installs and guarded retirement",
    "build: make TypeScript runtime reproducible and add cross-platform CI",
    "docs: align roadmap and release claims with executable gates",
    "release: finalize stable 6.0.1",
]
CHECKS: dict[str, list[str]] = {
    EXPECTED_MESSAGES[0]: ["artifact contracts", "immutable pending snapshots", "stale input/output", "state schema migration"],
    EXPECTED_MESSAGES[1]: ["correction sources", "legal-state matrix", "impossible states"],
    EXPECTED_MESSAGES[2]: ["NFR applicability uniqueness", "owner/NFR/acceptance traceability", "semantic fingerprint"],
    EXPECTED_MESSAGES[3]: ["lossless legacy backup", "validate to next", "explicit discovery migration", "semantic PASS preservation"],
    EXPECTED_MESSAGES[4]: ["immutable GitHub tree/blob install", "runtime JS/declarations", "guarded retirement backup"],
    EXPECTED_MESSAGES[5]: ["npm ci/test", "actual plugin API", "runtime drift", "native tools", "journey/symlink/journal/recovery"],
    EXPECTED_MESSAGES[6]: ["immutable README ref", "executable release claims", "full local regression"],
    EXPECTED_MESSAGES[7]: ["candidate matrix", "full local release gates", "fresh install/status/update"],
}


def clean(root: Path, *, dist_tools: bool = True) -> None:
    if dist_tools:
        shutil.rmtree(root / "dist-tools", ignore_errors=True)
    for candidate in root.rglob("__pycache__"):
        if candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)
    for candidate in root.rglob("*.pyc"):
        candidate.unlink(missing_ok=True)
    for relative in [".pytest_cache", ".mypy_cache"]:
        shutil.rmtree(root / relative, ignore_errors=True)


def configure(root: Path) -> None:
    common.run(["git", "config", "user.name", "OpenCode Agents Release Bot"], cwd=root)
    common.run(["git", "config", "user.email", "opencode-agents-release@users.noreply.github.com"], cwd=root)


def sync_target(root: Path) -> str:
    configure(root)
    common.run(["git", "fetch", "origin", common.TARGET_BRANCH, "--tags", "--force"], cwd=root)
    remote_line = common.run(["git", "ls-remote", "origin", f"refs/heads/{common.TARGET_BRANCH}"], cwd=root).stdout.strip()
    if not remote_line:
        raise RuntimeError(f"target branch does not exist: {common.TARGET_BRANCH}")
    remote = remote_line.split()[0]
    common.run(["git", "switch", "--detach", remote], cwd=root)
    common.assert_clean(root)
    return remote


def history(root: Path) -> list[dict[str, str]]:
    if common.run(["git", "rev-parse", f"{COMMIT_ONE}^"], cwd=root).stdout.strip() != BASE_COMMIT:
        raise RuntimeError("commit 1 no longer has the required TypeScript base parent")
    if common.run(["git", "rev-parse", f"{COMMIT_ONE}^^"], cwd=root).stdout.strip() != PYTHON_SNAPSHOT:
        raise RuntimeError("the required Python 6.0 snapshot is no longer the base grandparent")
    if common.run(["git", "merge-base", "--is-ancestor", COMMIT_ONE, "HEAD"], cwd=root, check=False).returncode != 0:
        raise RuntimeError(f"target head is not descended from required commit 1: {COMMIT_ONE}")
    shas = common.run(["git", "rev-list", "--reverse", f"{COMMIT_ONE}..HEAD"], cwd=root).stdout.splitlines()
    if len(shas) > len(EXPECTED_MESSAGES):
        raise RuntimeError(f"target contains more commits than the required chain: {shas}")
    result: list[dict[str, str]] = []
    previous = COMMIT_ONE
    for index, sha in enumerate(shas):
        message = common.run(["git", "show", "-s", "--format=%s", sha], cwd=root).stdout.strip()
        parent = common.run(["git", "rev-parse", f"{sha}^"], cwd=root).stdout.strip()
        if parent != previous:
            raise RuntimeError(f"target history is not linear at {sha}: expected parent {previous}, got {parent}")
        expected = EXPECTED_MESSAGES[index]
        if message != expected:
            raise RuntimeError(f"unexpected commit at position {index + 2}: expected {expected!r}, got {message!r}")
        result.append({"sha": sha, "message": message})
        previous = sha
    return result


def chain_metadata(root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = [
        {
            "message": "test: capture independent 6.0 release blockers",
            "sha": COMMIT_ONE,
            "checks": ["red controller blocker baseline", "red installer blocker baseline"],
        }
    ]
    for item in history(root):
        result.append({"message": item["message"], "sha": item["sha"], "checks": CHECKS[item["message"]]})
    return result


def sha_at(root: Path, required_position: int) -> str | None:
    # Position is one-based in the required chain: 1 is the test commit, 7 is build, 8 docs, 9 release.
    if required_position == 1:
        return COMMIT_ONE
    items = history(root)
    offset = required_position - 2
    return items[offset]["sha"] if 0 <= offset < len(items) else None


def report(summary: Path | None, item: dict[str, Any], *, reused: bool = False) -> None:
    suffix = " (already published and reused)" if reused else ""
    line = f"- `{item['sha']}` — {item['message']} — {', '.join(item['checks'])}{suffix}\n"
    print(line, end="")
    if summary:
        with summary.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"{name}={value}\n")


def write_json(candidate: Path, value: object) -> None:
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
