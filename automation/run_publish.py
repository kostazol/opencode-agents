from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

import common


ARTIFACT_BRANCH = "agent/6.0.1-independent-hardening-artifact"
ARTIFACT_NAME = "opencode-agents-6.0.1.zip"


def bytes_at(root: Path, commit: str, relative: str) -> bytes:
    process = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode != 0:
        raise RuntimeError(f"cannot read {relative} at {commit}: {process.stderr.decode('utf-8', errors='replace')}")
    return process.stdout


def create_and_verify_archive(root: Path, commit: str, result_dir: Path, log: Path) -> tuple[Path, str, int]:
    archive = result_dir / ARTIFACT_NAME
    common.run(["git", "archive", "--format=zip", f"--output={archive}", commit], cwd=root, log=log)
    expected = common.run(["git", "ls-tree", "-r", "--name-only", commit], cwd=root, log=log).stdout.splitlines()
    if not expected:
        raise RuntimeError("final Git tree is empty")
    with zipfile.ZipFile(archive, "r") as package:
        actual = sorted(name for name in package.namelist() if not name.endswith("/"))
        if actual != sorted(expected):
            raise RuntimeError(
                f"ZIP tree differs from Git tree: missing={sorted(set(expected) - set(actual))}, extra={sorted(set(actual) - set(expected))}"
            )
        for relative in expected:
            if package.read(relative) != bytes_at(root, commit, relative):
                raise RuntimeError(f"ZIP byte content differs from Git tree: {relative}")
        with tempfile.TemporaryDirectory(prefix="opencode-agents-unpack-") as temporary:
            unpacked = Path(temporary)
            package.extractall(unpacked)
            for relative in expected:
                candidate = unpacked.joinpath(*relative.split("/"))
                if not candidate.is_file() or candidate.read_bytes() != bytes_at(root, commit, relative):
                    raise RuntimeError(f"re-unpacked ZIP differs from Git tree: {relative}")
    digest = common.sha256_file(archive)
    if len(digest) != 64:
        raise RuntimeError("invalid SHA-256 result")
    return archive, digest, len(expected)


def draft_pr_body(release: dict[str, object], artifact: dict[str, object] | None = None) -> str:
    lines = [
        "## OpenCode Agents 6.0.1 independent hardening",
        "",
        "This draft PR contains the required nine-commit hardening chain from `7b43e411bc87da8182fa1c0c7a972b005831a573`.",
        "",
        "Architecture remains four semantic agents, one TypeScript controller, and three native OpenCode tools. No parallel Python controller, generic workflow framework, service, or database was added.",
        "",
        "### Commit chain",
        "",
    ]
    for item in release["commits"]:
        lines.append(f"- `{item['sha']}` — {item['message']}")
    lines.extend(
        [
            "",
            "### Executed gates",
            "",
            "- `npm ci`, `npm test`, actual `@opencode-ai/plugin` typecheck, and generated runtime drift check",
            "- complete artifact-producing store journey and stale input/output negatives",
            "- mocked immutable GitHub tree/blob install and guarded retirement/update",
            "- legacy validate → next, NFR adversarial, impossible-state, symlink, and journal conflict/recovery tests",
            "- Linux, Windows, and macOS on Node 20 and Node 22 for the code, release candidate, and final release trees",
            "- fresh install/status/update",
            "",
        ]
    )
    if artifact:
        lines.extend(
            [
                "### Exact final-tree archive",
                "",
                f"- Target Git tree: `{artifact['target_commit']}`",
                f"- Artifact commit: `{artifact['artifact_commit']}`",
                f"- SHA-256: `{artifact['zip_sha256']}`",
                f"- Files verified after re-unpack: `{artifact['file_count']}`",
                "",
            ]
        )
    lines.append("No merge is requested or performed by this workflow.")
    return "\n".join(lines) + "\n"


def ensure_draft_pr(root: Path, release: dict[str, object], log: Path) -> tuple[dict[str, object] | None, str | None]:
    listed = common.run(
        [
            "gh", "pr", "list", "--repo", common.REPO, "--state", "open",
            "--head", common.TARGET_BRANCH, "--base", "main", "--limit", "10",
            "--json", "number,url,isDraft,headRefName,baseRefName,title",
        ],
        cwd=root,
        log=log,
        check=False,
    )
    if listed.returncode != 0:
        return None, f"draft PR lookup failed under workflow token: {listed.stdout.strip()}"
    existing = json.loads(listed.stdout or "[]")
    if len(existing) > 1:
        raise RuntimeError(f"more than one open PR exists for the exact head/base: {existing}")
    if existing:
        pr = existing[0]
        if pr["headRefName"] != common.TARGET_BRANCH or pr["baseRefName"] != "main":
            raise RuntimeError(f"existing PR has wrong head/base: {pr}")
        if not pr["isDraft"]:
            converted = common.run(["gh", "pr", "ready", "--undo", str(pr["number"]), "--repo", common.REPO], cwd=root, log=log, check=False)
            if converted.returncode != 0:
                return None, f"existing PR could not be converted to draft: {converted.stdout.strip()}"
            pr["isDraft"] = True
        return pr, None

    body_file = root.parent / "draft-pr-body.md"
    body_file.write_text(draft_pr_body(release), encoding="utf-8", newline="\n")
    created = common.run(
        [
            "gh", "pr", "create", "--repo", common.REPO, "--draft", "--base", "main",
            "--head", common.TARGET_BRANCH,
            "--title", "release: OpenCode Agents 6.0.1 independent hardening",
            "--body-file", str(body_file),
        ],
        cwd=root,
        log=log,
        check=False,
    )
    if created.returncode != 0:
        return None, f"draft PR creation is disabled for the workflow token: {created.stdout.strip()}"
    url = created.stdout.strip().splitlines()[-1]
    viewed = common.run(
        ["gh", "pr", "view", url, "--repo", common.REPO, "--json", "number,url,isDraft,headRefName,baseRefName,title"],
        cwd=root,
        log=log,
    )
    pr = json.loads(viewed.stdout)
    if not pr["isDraft"] or pr["headRefName"] != common.TARGET_BRANCH or pr["baseRefName"] != "main":
        raise RuntimeError(f"created PR does not satisfy exact draft/base/head contract: {pr}")
    return pr, None


def publish_artifact_branch(
    root: Path,
    release: dict[str, object],
    archive: Path,
    digest: str,
    file_count: int,
    pr: dict[str, object] | None,
    final_matrix: dict[str, object],
    result_dir: Path,
    log: Path,
) -> dict[str, object]:
    existing = common.run(["git", "ls-remote", "origin", f"refs/heads/{ARTIFACT_BRANCH}"], cwd=root, log=log).stdout.strip()
    if existing:
        raise RuntimeError(f"artifact branch already exists; refusing to rewrite without force: {existing}")

    target_commit = release["sha9"]
    common.run(["git", "switch", "--detach", target_commit], cwd=root, log=log)
    common.run(["git", "switch", "-c", ARTIFACT_BRANCH], cwd=root, log=log)
    destination = root / ".release" / ARTIFACT_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archive, destination)
    (root / ".release" / f"{ARTIFACT_NAME}.sha256").write_text(f"{digest}  {ARTIFACT_NAME}\n", encoding="utf-8", newline="\n")
    chain = "\n".join(f"{item['sha']} {item['message']}" for item in release["commits"]) + "\n"
    (root / ".release" / "commit-chain.txt").write_text(chain, encoding="utf-8", newline="\n")
    metadata = {
        "schema_version": 1,
        "release": "6.0.1",
        "target_branch": common.TARGET_BRANCH,
        "target_commit": target_commit,
        "artifact_branch": ARTIFACT_BRANCH,
        "zip": ARTIFACT_NAME,
        "zip_sha256": digest,
        "file_count": file_count,
        "verified_against_exact_git_tree": True,
        "verified_after_re_unpack": True,
        "commit_chain": release["commits"],
        "matrix_code": release["matrix_code"],
        "matrix_candidate": release["matrix_candidate"],
        "matrix_final": final_matrix,
        "pull_request": pr,
        "environment_blocked": release.get("environment_blocked", []),
    }
    (root / ".release" / "result.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    changed = common.git_changed(root)
    expected = sorted(
        [
            f".release/{ARTIFACT_NAME}",
            f".release/{ARTIFACT_NAME}.sha256",
            ".release/commit-chain.txt",
            ".release/result.json",
        ]
    )
    if changed != expected:
        raise RuntimeError(f"unexpected artifact branch changes: {changed}")
    common.run(["git", "add", "--", *changed], cwd=root, log=log)
    common.run(["git", "commit", "-m", "release-artifact: publish exact 6.0.1 tree archive"], cwd=root, log=log)
    artifact_commit = common.run(["git", "rev-parse", "HEAD"], cwd=root, log=log).stdout.strip()
    common.run(["git", "push", "origin", f"HEAD:{ARTIFACT_BRANCH}"], cwd=root, log=log)
    remote = common.run(["git", "ls-remote", "origin", f"refs/heads/{ARTIFACT_BRANCH}"], cwd=root, log=log).stdout.split()[0]
    if remote != artifact_commit:
        raise RuntimeError(f"artifact branch remote mismatch: local={artifact_commit}, remote={remote}")
    common.assert_clean(root)

    result = dict(metadata)
    result["artifact_commit"] = artifact_commit
    result["download_url"] = f"https://raw.githubusercontent.com/{common.REPO}/{artifact_commit}/.release/{ARTIFACT_NAME}"
    result["sha256_url"] = f"https://raw.githubusercontent.com/{common.REPO}/{artifact_commit}/.release/{ARTIFACT_NAME}.sha256"
    result["pull_request"] = pr
    (result_dir / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def update_pr(root: Path, pr: dict[str, object] | None, release: dict[str, object], artifact: dict[str, object], log: Path) -> None:
    if not pr:
        return
    body_file = root.parent / "draft-pr-final-body.md"
    body_file.write_text(draft_pr_body(release, artifact), encoding="utf-8", newline="\n")
    common.run(
        ["gh", "pr", "edit", str(pr["number"]), "--repo", common.REPO, "--body-file", str(body_file)],
        cwd=root,
        log=log,
        check=False,
    )


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: run_publish.py <automation-checkout> <target-checkout> <release-json> <result-dir>")
    automation_root = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    release_path = Path(sys.argv[3]).resolve()
    result_dir = Path(sys.argv[4]).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    log = result_dir / "10-publish.log"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    sha9 = release["sha9"]

    common.run(["git", "config", "user.name", "OpenCode Agents Release Bot"], cwd=root)
    common.run(["git", "config", "user.email", "opencode-agents-release@users.noreply.github.com"], cwd=root)
    common.run(["git", "fetch", "origin", common.TARGET_BRANCH, "--force"], cwd=root)
    head = common.run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    remote = common.run(["git", "ls-remote", "origin", f"refs/heads/{common.TARGET_BRANCH}"], cwd=root).stdout.split()[0]
    if head != sha9 or remote != sha9:
        raise RuntimeError(f"publish stage must use exact final target tree: local={head}, remote={remote}, expected={sha9}")
    common.assert_clean(root)

    final_matrix = {
        "status": "passed",
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "url": f"https://github.com/{common.REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
        "commit": sha9,
        "platforms": ["ubuntu-latest", "windows-latest", "macos-latest"],
        "node": [20, 22],
    }
    archive, digest, file_count = create_and_verify_archive(root, sha9, result_dir, log)
    pr, pr_blocker = ensure_draft_pr(root, release, log)
    if pr_blocker:
        release.setdefault("environment_blocked", []).append(pr_blocker)
    artifact = publish_artifact_branch(root, release, archive, digest, file_count, pr, final_matrix, result_dir, log)
    update_pr(root, pr, release, artifact, log)

    shutil.copy2(root / ".release" / f"{ARTIFACT_NAME}.sha256", result_dir / f"{ARTIFACT_NAME}.sha256")
    summary = [
        "## OpenCode Agents 6.0.1 publication",
        "",
        f"- Final target commit: `{sha9}`",
        f"- Artifact commit: `{artifact['artifact_commit']}`",
        f"- ZIP SHA-256: `{digest}`",
        f"- Re-unpacked files verified: `{file_count}`",
        f"- Draft PR: `{pr['url'] if pr else 'environment-blocked; connector follow-up required'}`",
        f"- Download: `{artifact['download_url']}`",
        "",
    ]
    text = "\n".join(summary)
    print(text)
    (result_dir / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    common.run(["git", "rev-parse", "HEAD"], cwd=automation_root, log=log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
