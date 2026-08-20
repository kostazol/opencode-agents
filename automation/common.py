from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Iterable, Mapping, Sequence

REPO = "kostazol/opencode-agents"
TARGET_BRANCH = "agent/6.0.1-independent-hardening"
BASELINE_SHA = "6a8baa4b70d6157e28661a8bae17b8c4b93ef779"


def run(
    command: Sequence[str] | str,
    *,
    cwd: Path,
    check: bool = True,
    env: Mapping[str, str] | None = None,
    log: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    shell = isinstance(command, str)
    process = subprocess.run(
        command,
        cwd=cwd,
        env=merged,
        shell=shell,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    rendered = command if isinstance(command, str) else " ".join(command)
    output = f"$ {rendered}\n{process.stdout}\n[exit={process.returncode}]\n"
    sys.stdout.write(output)
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(output)
    if check and process.returncode != 0:
        raise RuntimeError(f"command failed ({process.returncode}): {rendered}")
    return process


def expect_failure(command: Sequence[str] | str, *, cwd: Path, log: Path) -> None:
    result = run(command, cwd=cwd, check=False, log=log)
    if result.returncode == 0:
        raise RuntimeError(f"negative test unexpectedly passed: {command}")


def write_files(root: Path, files: Mapping[str, str | bytes]) -> list[str]:
    changed: list[str] = []
    for relative, content in files.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            previous = destination.read_bytes() if destination.exists() else None
            if previous == content:
                continue
            destination.write_bytes(content)
        else:
            normalized = content.replace("\r\n", "\n")
            if not normalized.endswith("\n"):
                normalized += "\n"
            previous = destination.read_text(encoding="utf-8") if destination.exists() else None
            if previous == normalized:
                continue
            destination.write_text(normalized, encoding="utf-8", newline="\n")
        changed.append(relative)
    return changed


def remove_paths(root: Path, paths: Iterable[str]) -> list[str]:
    changed: list[str] = []
    for relative in paths:
        candidate = root / relative
        if candidate.is_dir() and not candidate.is_symlink():
            shutil.rmtree(candidate)
            changed.append(relative)
        elif candidate.exists() or candidate.is_symlink():
            candidate.unlink()
            changed.append(relative)
    return changed


def git_changed(root: Path) -> list[str]:
    result = run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=root,
    ).stdout
    paths: list[str] = []
    records = result.split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        if not record:
            index += 1
            continue
        status = record[:2]
        path = record[3:]
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            index += 1
            if index >= len(records):
                raise RuntimeError("malformed git porcelain rename record")
            path = records[index]
        paths.append(path.replace("\\", "/"))
        index += 1
    return sorted(set(paths))


def commit_and_push(
    root: Path,
    message: str,
    allowed: Iterable[str],
    *,
    log: Path,
) -> str:
    allowed_set = {item.replace("\\", "/").rstrip("/") for item in allowed}
    changed = git_changed(root)
    unexpected = [
        item
        for item in changed
        if not any(item == prefix or item.startswith(prefix + "/") for prefix in allowed_set)
    ]
    if unexpected:
        raise RuntimeError(f"unexpected changed paths before {message!r}: {unexpected}")
    if not changed:
        raise RuntimeError(f"no changes for required commit {message!r}")
    run(["git", "add", "--", *changed], cwd=root, log=log)
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=root, log=log).stdout.splitlines()
    if sorted(staged) != sorted(changed):
        raise RuntimeError(f"staged paths differ from confirmed paths: staged={staged}, changed={changed}")
    run(["git", "commit", "-m", message], cwd=root, log=log)
    sha = run(["git", "rev-parse", "HEAD"], cwd=root, log=log).stdout.strip()
    run(["git", "push", "origin", f"HEAD:{TARGET_BRANCH}"], cwd=root, log=log)
    remote = run(["git", "ls-remote", "origin", f"refs/heads/{TARGET_BRANCH}"], cwd=root, log=log).stdout.split()[0]
    if remote != sha:
        raise RuntimeError(f"remote head mismatch after push: local={sha}, remote={remote}")
    return sha


def sha256_file(candidate: Path) -> str:
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_clean(root: Path) -> None:
    changed = git_changed(root)
    if changed:
        raise RuntimeError(f"worktree is not clean: {changed}")


def npm_exec(root: Path, args: Sequence[str], *, log: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    executable = "npm.cmd" if os.name == "nt" else "npm"
    return run([executable, *args], cwd=root, log=log, check=check)


def node_test(root: Path, files: Sequence[str], *, log: Path, pattern: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["node", "--test"]
    if pattern:
        command.append(f"--test-name-pattern={pattern}")
    command.extend(files)
    return run(command, cwd=root, log=log, check=check)


def compile_runtime(root: Path, *, log: Path) -> None:
    run(
        ["npx", "--yes", "-p", "typescript@5.6.3", "tsc", "-p", "tsconfig.json"],
        cwd=root,
        log=log,
    )


def wait_for_workflow(
    *,
    root: Path,
    workflow: str,
    commit: str,
    log: Path,
    timeout_seconds: int = 3600,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, object] | None = None
    while time.monotonic() < deadline:
        result = run(
            [
                "gh",
                "run",
                "list",
                "--repo",
                REPO,
                "--workflow",
                workflow,
                "--commit",
                commit,
                "--limit",
                "20",
                "--json",
                "databaseId,status,conclusion,headSha,url,event,createdAt",
            ],
            cwd=root,
            log=log,
        )
        runs = json.loads(result.stdout or "[]")
        matching = [item for item in runs if item.get("headSha") == commit and item.get("event") in {"push", "pull_request", "workflow_dispatch"}]
        if matching:
            matching.sort(key=lambda item: str(item.get("createdAt", "")), reverse=True)
            last = matching[0]
            if last.get("status") == "completed":
                if last.get("conclusion") != "success":
                    run(["gh", "run", "view", str(last["databaseId"]), "--repo", REPO, "--log-failed"], cwd=root, log=log, check=False)
                    raise RuntimeError(f"workflow {workflow} failed for {commit}: {last}")
                return last
        time.sleep(15)
    raise RuntimeError(f"workflow {workflow} did not complete for {commit}; last={last}")


def json_dump(candidate: Path, value: object) -> None:
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
