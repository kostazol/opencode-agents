from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from bootstrap import AUTOMATION, common, sync_target, write_json

SPEC = importlib.util.spec_from_file_location("hardening_publish_v1", AUTOMATION / "run_publish.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load publication helpers")
publish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish)


def git_bytes(root: Path, object_name: str) -> bytes:
    process = subprocess.run(["git", "show", object_name], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 0:
        raise RuntimeError(f"cannot read Git object {object_name}: {process.stderr.decode('utf-8', errors='replace')}")
    return process.stdout


def reuse_artifact(
    root: Path,
    artifact_commit: str,
    release: dict[str, object],
    archive: Path,
    digest: str,
    file_count: int,
    final_matrix: dict[str, object],
    pr: dict[str, object] | None,
    result_dir: Path,
) -> dict[str, object]:
    stored_archive = git_bytes(root, f"{artifact_commit}:.release/{publish.ARTIFACT_NAME}")
    if stored_archive != archive.read_bytes():
        raise RuntimeError("existing artifact branch ZIP is not the deterministic archive of the exact final tree")
    stored_digest = git_bytes(root, f"{artifact_commit}:.release/{publish.ARTIFACT_NAME}.sha256").decode("utf-8").split()[0]
    if stored_digest != digest:
        raise RuntimeError(f"existing artifact branch SHA-256 mismatch: expected={digest}, actual={stored_digest}")
    metadata = json.loads(git_bytes(root, f"{artifact_commit}:.release/result.json").decode("utf-8"))
    if metadata.get("target_commit") != release["sha9"] or metadata.get("zip_sha256") != digest or metadata.get("file_count") != file_count:
        raise RuntimeError(f"existing artifact metadata does not match the final release: {metadata}")
    result = dict(metadata)
    result.update(
        {
            "artifact_commit": artifact_commit,
            "download_url": f"https://raw.githubusercontent.com/{common.REPO}/{artifact_commit}/.release/{publish.ARTIFACT_NAME}",
            "sha256_url": f"https://raw.githubusercontent.com/{common.REPO}/{artifact_commit}/.release/{publish.ARTIFACT_NAME}.sha256",
            "matrix_final": final_matrix,
            "pull_request": pr or metadata.get("pull_request"),
            "environment_blocked": release.get("environment_blocked", []),
        }
    )
    (result_dir / publish.ARTIFACT_NAME).write_bytes(stored_archive)
    (result_dir / f"{publish.ARTIFACT_NAME}.sha256").write_text(
        f"{digest}  {publish.ARTIFACT_NAME}\n", encoding="utf-8", newline="\n"
    )
    write_json(result_dir / "result.json", result)
    return result


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

    remote = sync_target(root)
    if remote != sha9:
        raise RuntimeError(f"publication must use exact final target tree: remote={remote}, expected={sha9}")
    final_matrix = {
        "status": "passed",
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "url": f"https://github.com/{common.REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
        "commit": sha9,
        "platforms": ["ubuntu-latest", "windows-latest", "macos-latest"],
        "node": [20, 22],
    }
    archive, digest, file_count = publish.create_and_verify_archive(root, sha9, result_dir, log)
    pr, pr_blocker = publish.ensure_draft_pr(root, release, log)
    if pr_blocker:
        release.setdefault("environment_blocked", []).append(pr_blocker)

    existing_line = common.run(
        ["git", "ls-remote", "origin", f"refs/heads/{publish.ARTIFACT_BRANCH}"], cwd=root, log=log
    ).stdout.strip()
    if existing_line:
        artifact_commit = existing_line.split()[0]
        common.run(["git", "fetch", "origin", publish.ARTIFACT_BRANCH, "--force"], cwd=root, log=log)
        artifact = reuse_artifact(root, artifact_commit, release, archive, digest, file_count, final_matrix, pr, result_dir)
    else:
        artifact = publish.publish_artifact_branch(root, release, archive, digest, file_count, pr, final_matrix, result_dir, log)
        shutil.copy2(root / ".release" / f"{publish.ARTIFACT_NAME}.sha256", result_dir / f"{publish.ARTIFACT_NAME}.sha256")
    publish.update_pr(root, pr, release, artifact, log)

    summary = "\n".join(
        [
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
    )
    print(summary)
    (result_dir / "summary.md").write_text(summary, encoding="utf-8", newline="\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(summary)
    common.run(["git", "rev-parse", "HEAD"], cwd=automation_root, log=log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
