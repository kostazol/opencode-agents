#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

VERSION = "6.0.1"
DEFAULT_REPO = "kostazol/opencode-agents"
DEFAULT_REF = "v6.0.1"
MANIFEST_NAME = ".opencode-agents-manifest.json"
SOURCE_REF_NAME = ".opencode-agents-source-ref"

# Generated from exact historical Git objects. A path is retired only when its
# current SHA-256 is present here; unknown/customized files are never deleted.
RETIREMENT_MANIFESTS: dict[str, set[str]] = {
    'runtime/orchestrator.py': {'baca0c85afe8572bde2ee924b64562bcbcf63896f2247316ee548d8fee56b34b'},
    'runtime/orchestrator_core/__init__.py': {'17a0fcda3c91f6ad1bd411b47012630da3073a94379a2cfb693a6656623d1508'},
    'runtime/orchestrator_core/action_builder.py': {'57cf2e8b69576cd23261cf9711cff60d95d431cc9e09484f2adb18438c86f4d1'},
    'runtime/orchestrator_core/controller.py': {'f108e1eeeeddac0e027eebd2d70adae2c64ff6eb4a7d41d4a18270cc58a7bb36'},
    'runtime/orchestrator_core/convergence.py': {'f9fab741d3310707dcf444ac4c9dd6d8c2701006b67eb85746c438dc3c799743'},
    'runtime/orchestrator_core/event_support.py': {'e30fe5300d36bcad45d6e5caff48d1d1c5fb5b952f196623b6fcdbed3453a56b'},
    'runtime/orchestrator_core/events.py': {'cac7ea9669068cc551bc562f34434b6326793c61225e3dc0b4b9a37d1b712094'},
    'runtime/orchestrator_core/io.py': {'3cd1d9e1bde89fd992a92e6a3531f82af3474b9ffe6a1a5f3da71042aaa8d688'},
    'runtime/orchestrator_core/legacy.py': {'c6b3c15f165a2beb09b64367d31178ac1954dcfee716ca9170f5ebdad1d0cdd8'},
    'runtime/orchestrator_core/migration.py': {'41b4024dcf9b8c7359af9ee687294bcd2e63c0825c777ba8061f5d0ff7ea7390'},
    'runtime/orchestrator_core/model.py': {'fa6add900ba17b0e0db429d750a9dc3aeacb6f465ad09f8105f625cdae90d8a5'},
    'runtime/orchestrator_core/non_stage_events.py': {'d235072b8e11e6daea60fe0fa168ed66b7efda106a0e5f38fa1371d9ceb5c3d4'},
    'runtime/orchestrator_core/protocol.py': {'e5deeb3c1ec2d3162b63b857180d62ca175fd2baf79d8f9ed49aaa1d4b09ade5'},
    'runtime/orchestrator_core/render.py': {'ffc45b1a8343053967c6b2f200e6875b25fe6e1dfbae4fcd2a58dcaa7536c1fa'},
    'runtime/orchestrator_core/reopening.py': {'17311a773ae30c93be536397dbb4d4fe5e5ea1f5934a01769c2b3c248290dd68'},
    'runtime/orchestrator_core/routing.py': {'6ae7f08e981d27f7d9cef05785e8d6e4a96bb19e05f3a2bd9d4a702aae976385'},
    'runtime/orchestrator_core/stage_events.py': {'a7e09b39724aeb8c44058c691ca3867f9453419a54b3634537834d2d7d7e6981'},
    'runtime/orchestrator_core/state_types.py': {'51e1ff52ad58119152c9be0d412712035c117500fb78faa1f749633c5fed0753'},
    'runtime/orchestrator_core/state_validation.py': {'0ac327ef620409c4a00d4718fb38b9393847e7d794c0775598f1d80dbb4acf74'},
    'runtime/orchestrator_core/store.py': {'c7019eccac94123bd13f52ec6acb4d19c06879c49eb20c9a650bb5aa73e36a0c'},
    'runtime/orchestrator_core/traceability.py': {'a044a9f8cd317ed47b48be06a8742fa440b5dd926022b09ebfa828ab792a0745'},
}


class InstallerError(RuntimeError):
    pass


class FileRecord:
    def __init__(self, path: str, sha256: str, size: int) -> None:
        self.path = path
        self.sha256 = sha256
        self.size = size


def _canonical_relative(value: str) -> str:
    normalized = value.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if not normalized or candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        raise InstallerError(f"unsafe relative path: {value!r}")
    canonical = candidate.as_posix()
    if canonical != normalized:
        raise InstallerError(f"non-canonical relative path: {value!r}")
    return canonical


def installable(relative: str) -> bool:
    try:
        canonical = _canonical_relative(relative)
    except InstallerError:
        return False
    candidate = PurePosixPath(canonical)
    if len(candidate.parts) < 2:
        return canonical in {"LICENSE", "NOTICE"}
    root = candidate.parts[0]
    suffixes = "".join(candidate.suffixes)
    if root == "agents":
        return candidate.suffix == ".md"
    if root == "runtime":
        return candidate.suffix == ".js" or suffixes.endswith(".d.ts") or candidate.suffix == ".json"
    if root == "tools":
        return candidate.suffix in {".ts", ".js"} or suffixes.endswith(".d.ts")
    if root == "skills":
        return candidate.suffix in {".md", ".json", ".js", ".ts"} or suffixes.endswith(".d.ts")
    return False


def api_json(url: str) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"opencode-agents-installer/{VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read()
    except HTTPError as error:
        raise InstallerError(f"GitHub API returned HTTP {error.code} for {url}") from error
    except URLError as error:
        raise InstallerError(f"GitHub API request failed for {url}: {error.reason}") from error
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstallerError(f"GitHub API returned invalid JSON for {url}") from error


def _git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def _resolve_commit(repo: str, ref: str) -> str:
    if not repo or repo.count("/") != 1:
        raise InstallerError(f"repository must be owner/name, got {repo!r}")
    if not ref or any(character.isspace() for character in ref):
        raise InstallerError("remote ref must be non-empty and contain no whitespace")
    commit = api_json(f"https://api.github.com/repos/{repo}/commits/{quote(ref, safe='')}")
    if not isinstance(commit, dict) or not isinstance(commit.get("sha"), str) or not commit["sha"]:
        raise InstallerError("GitHub commit response has no sha")
    sha = commit["sha"]
    if not all(character in "0123456789abcdefABCDEF" for character in sha) or len(sha) != 40:
        raise InstallerError(f"GitHub returned a non-immutable commit sha: {sha!r}")
    return sha.lower()


def _remote_tree(repo: str, commit_sha: str, destination: Path) -> None:
    tree = api_json(f"https://api.github.com/repos/{repo}/git/trees/{commit_sha}?recursive=1")
    if not isinstance(tree, dict) or tree.get("truncated"):
        raise InstallerError("GitHub recursive tree is missing or truncated")
    entries = tree.get("tree")
    if not isinstance(entries, list):
        raise InstallerError("GitHub tree response has no tree array")
    selected = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "blob" or not isinstance(entry.get("path"), str):
            continue
        relative = entry["path"]
        if installable(relative):
            selected.append(entry)
    if not selected:
        raise InstallerError("immutable package tree contains no installable files")
    for entry in selected:
        relative = _canonical_relative(entry["path"])
        blob_sha = entry.get("sha")
        if not isinstance(blob_sha, str) or not blob_sha:
            raise InstallerError(f"tree entry has no blob sha: {relative}")
        blob = api_json(f"https://api.github.com/repos/{repo}/git/blobs/{blob_sha}")
        if not isinstance(blob, dict) or blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
            raise InstallerError(f"GitHub blob response is invalid: {relative}")
        try:
            content = base64.b64decode(blob["content"], validate=False)
        except ValueError as error:
            raise InstallerError(f"GitHub blob is not valid base64: {relative}") from error
        if len(blob_sha) == 40 and all(character in "0123456789abcdefABCDEF" for character in blob_sha):
            actual = _git_blob_sha(content)
            if actual.lower() != blob_sha.lower():
                raise InstallerError(f"Git blob digest mismatch for {relative}: expected {blob_sha}, got {actual}")
        target = destination.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


@contextmanager
def prepared_source(source: str | os.PathLike[str] | None, repo: str = DEFAULT_REPO, ref: str = DEFAULT_REF) -> Iterator[Path]:
    if source is not None:
        root = Path(source).expanduser().resolve()
        if not root.is_dir():
            raise InstallerError(f"source directory does not exist: {root}")
        immutable = "local"
        try:
            immutable = subprocess_sha(root)
        except InstallerError:
            pass
        marker = root / SOURCE_REF_NAME
        temporary_marker = not marker.exists()
        if temporary_marker:
            marker.write_text(immutable + "\n", encoding="utf-8")
        try:
            yield root
        finally:
            if temporary_marker:
                marker.unlink(missing_ok=True)
        return

    commit_sha = _resolve_commit(repo, ref)
    with tempfile.TemporaryDirectory(prefix="opencode-agents-") as temporary:
        root = Path(temporary)
        _remote_tree(repo, commit_sha, root)
        (root / SOURCE_REF_NAME).write_text(commit_sha + "\n", encoding="utf-8")
        yield root


def subprocess_sha(root: Path) -> str:
    import subprocess

    process = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    value = process.stdout.strip()
    if process.returncode or len(value) != 40 or any(character not in "0123456789abcdefABCDEF" for character in value):
        raise InstallerError("local source is not an exact Git commit")
    return value.lower()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(candidate: Path) -> str:
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_target(target: Path, relative: str) -> Path:
    canonical = _canonical_relative(relative)
    root = target.resolve()
    candidate = target.joinpath(*PurePosixPath(canonical).parts)
    current = target
    for part in PurePosixPath(canonical).parts[:-1]:
        current = current / part
        if current.is_symlink():
            resolved = current.resolve()
            try:
                resolved.relative_to(root)
            except ValueError as error:
                raise InstallerError(f"target symlink escapes installation root: {canonical}") from error
    resolved_parent = candidate.parent.resolve(strict=False)
    try:
        resolved_parent.relative_to(root)
    except ValueError as error:
        raise InstallerError(f"target path escapes installation root: {canonical}") from error
    if candidate.is_symlink():
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise InstallerError(f"target file symlink escapes installation root: {canonical}") from error
    return candidate


def _backup_file(candidate: Path, target: Path, backup: Path, relative: str, dry_run: bool) -> None:
    if not candidate.exists() and not candidate.is_symlink():
        return
    destination = backup.joinpath(*PurePosixPath(relative).parts)
    if dry_run:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if candidate.is_symlink():
        destination.write_text(f"SYMLINK -> {os.readlink(candidate)}\n", encoding="utf-8")
    else:
        shutil.copy2(candidate, destination)


def _read_manifest(target: Path) -> dict[str, Any] | None:
    candidate = target / MANIFEST_NAME
    if not candidate.exists():
        return None
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InstallerError(f"cannot read existing manifest: {candidate}") from error
    if not isinstance(value, dict) or not isinstance(value.get("files"), list):
        raise InstallerError(f"existing manifest has invalid schema: {candidate}")
    return value


def _source_records(source: Path) -> list[FileRecord]:
    records: list[FileRecord] = []
    for candidate in sorted(source.rglob("*")):
        if not candidate.is_file() or candidate.is_symlink():
            continue
        relative = candidate.relative_to(source).as_posix()
        if not installable(relative):
            continue
        content = candidate.read_bytes()
        records.append(FileRecord(relative, sha256_bytes(content), len(content)))
    if not records:
        raise InstallerError("source contains no installable files")
    required_roots = {PurePosixPath(record.path).parts[0] for record in records}
    missing = {"agents", "runtime", "tools"} - required_roots
    if missing:
        raise InstallerError(f"source package is incomplete; missing roots: {sorted(missing)}")
    return records


def _retire_known(target: Path, backup: Path, dry_run: bool) -> tuple[list[str], list[str]]:
    retired: list[str] = []
    preserved: list[str] = []
    for relative, allowed_hashes in sorted(RETIREMENT_MANIFESTS.items()):
        canonical = _canonical_relative(relative)
        candidate = _safe_target(target, canonical)
        if not candidate.exists() and not candidate.is_symlink():
            continue
        if candidate.is_symlink() or not candidate.is_file():
            preserved.append(canonical)
            continue
        actual = sha256_file(candidate)
        if actual not in allowed_hashes:
            preserved.append(canonical)
            continue
        _backup_file(candidate, target, backup, canonical, dry_run)
        if not dry_run:
            candidate.unlink()
        retired.append(canonical)
    core = target / "runtime" / "orchestrator_core"
    if core.is_dir() and not core.is_symlink() and not any(core.iterdir()) and not dry_run:
        core.rmdir()
    return retired, preserved


def _remove_obsolete_managed(target: Path, backup: Path, manifest: dict[str, Any] | None, source_paths: set[str], dry_run: bool) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    preserved: list[str] = []
    if not manifest:
        return removed, preserved
    for record in manifest.get("files", []):
        if not isinstance(record, dict) or not isinstance(record.get("path"), str) or not isinstance(record.get("sha256"), str):
            continue
        relative = _canonical_relative(record["path"])
        if relative in source_paths:
            continue
        candidate = _safe_target(target, relative)
        if not candidate.exists() or candidate.is_symlink() or not candidate.is_file():
            if candidate.exists() or candidate.is_symlink():
                preserved.append(relative)
            continue
        if sha256_file(candidate) != record["sha256"]:
            preserved.append(relative)
            continue
        _backup_file(candidate, target, backup, relative, dry_run)
        if not dry_run:
            candidate.unlink()
        removed.append(relative)
    return removed, preserved


def install_or_update(
    source: str | os.PathLike[str],
    target: str | os.PathLike[str],
    update: bool = False,
    backup: str | os.PathLike[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    source_root = Path(source).resolve()
    target_root = Path(target).expanduser().resolve()
    if not source_root.is_dir():
        raise InstallerError(f"source directory does not exist: {source_root}")
    records = _source_records(source_root)
    existing = _read_manifest(target_root) if target_root.exists() else None
    if existing and not update:
        raise InstallerError("installation already exists; use update")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = Path(backup).expanduser().resolve() if backup else target_root.parent / f"{target_root.name}.backup-{timestamp}"
    if backup_root == target_root or target_root in backup_root.parents:
        raise InstallerError("backup must be outside the installation target")
    if backup_root.exists() and any(backup_root.iterdir()):
        raise InstallerError(f"backup directory is not empty: {backup_root}")

    source_ref_file = source_root / SOURCE_REF_NAME
    source_ref = source_ref_file.read_text(encoding="utf-8").strip() if source_ref_file.exists() else "local"
    source_paths = {record.path for record in records}
    copied: list[str] = []
    backed_up: list[str] = []
    if not dry_run:
        target_root.mkdir(parents=True, exist_ok=True)

    for record in records:
        source_file = source_root.joinpath(*PurePosixPath(record.path).parts)
        destination = _safe_target(target_root, record.path)
        if destination.exists() or destination.is_symlink():
            _backup_file(destination, target_root, backup_root, record.path, dry_run)
            backed_up.append(record.path)
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
            temporary.write_bytes(source_file.read_bytes())
            os.replace(temporary, destination)
        copied.append(record.path)

    removed, preserved_managed = _remove_obsolete_managed(target_root, backup_root, existing, source_paths, dry_run)
    retired, preserved_retirement = _retire_known(target_root, backup_root, dry_run)
    manifest = {
        "schema_version": 1,
        "package_version": VERSION,
        "source_ref": source_ref,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "files": [record.__dict__ for record in records],
    }
    if not dry_run:
        manifest_path = target_root / MANIFEST_NAME
        temporary = manifest_path.with_name(f".{manifest_path.name}.tmp-{os.getpid()}")
        temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, manifest_path)
    return {
        "operation": "update" if update else "install",
        "version": VERSION,
        "source_ref": source_ref,
        "target": str(target_root),
        "backup": str(backup_root),
        "copied": copied,
        "backed_up": backed_up,
        "removed_managed": removed,
        "retired_known": retired,
        "preserved_customized": sorted(set(preserved_managed + preserved_retirement)),
        "dry_run": dry_run,
    }


def status(target: str | os.PathLike[str]) -> dict[str, Any]:
    target_root = Path(target).expanduser().resolve()
    manifest = _read_manifest(target_root) if target_root.exists() else None
    if not manifest:
        return {"installed": False, "ok": False, "target": str(target_root), "missing": [], "modified": []}
    missing: list[str] = []
    modified: list[str] = []
    for record in manifest["files"]:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str) or not isinstance(record.get("sha256"), str):
            modified.append("<invalid-manifest-record>")
            continue
        relative = _canonical_relative(record["path"])
        candidate = _safe_target(target_root, relative)
        if not candidate.exists() or candidate.is_symlink() or not candidate.is_file():
            missing.append(relative)
        elif sha256_file(candidate) != record["sha256"]:
            modified.append(relative)
    retirement_candidates = []
    for relative in RETIREMENT_MANIFESTS:
        candidate = _safe_target(target_root, relative)
        if candidate.exists() or candidate.is_symlink():
            retirement_candidates.append(relative)
    return {
        "installed": True,
        "ok": not missing and not modified and not retirement_candidates,
        "target": str(target_root),
        "package_version": manifest.get("package_version"),
        "source_ref": manifest.get("source_ref"),
        "missing": missing,
        "modified": modified,
        "retirement_candidates": retirement_candidates,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install or update OpenCode semantic agents from one immutable package tree")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("install", "update"):
        operation = subparsers.add_parser(command)
        operation.add_argument("--source", help="local exact Git checkout; omit for GitHub immutable tree install")
        operation.add_argument("--repo", default=DEFAULT_REPO)
        operation.add_argument("--ref", default=DEFAULT_REF, help="tag, branch, or commit; resolved once to an immutable commit SHA")
        operation.add_argument("--target", required=True)
        operation.add_argument("--backup")
        operation.add_argument("--dry-run", action="store_true")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--target", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "status":
            result = status(args.target)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["ok"] else 1
        with prepared_source(args.source, args.repo, args.ref) as source:
            result = install_or_update(source, args.target, update=args.command == "update", backup=args.backup, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except InstallerError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
