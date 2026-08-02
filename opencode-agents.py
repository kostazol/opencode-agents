#!/usr/bin/env python3
"""Install and update OpenCode agents and plugins."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from contextlib import contextmanager
import uuid
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


VERSION = "2.4.0"
DEFAULT_REPOSITORY = "https://github.com/kostazol/opencode-agents"
DEFAULT_GITHUB_API = "https://api.github.com"
GROUP_PATTERNS = {"agents": "*.md", "plugins": "*.js"}
GROUPS = tuple(GROUP_PATTERNS)
MAX_SOURCE_FILE_BYTES = 1_000_000
MAX_GITHUB_RESPONSE_BYTES = 2_000_000
MAX_SOURCE_FILES = 100
MAX_SOURCE_TOTAL_BYTES = 5_000_000
OWNED_PREVIOUS_FILE_HASHES = {
    Path("plugins/analyst-workflow-guard.js"): frozenset({
        "2a4c3223c4283526105123f3661881a455b9b57b15a6290aae479d839ab66bc1",
        "f170158806b988411e3cd875e64a48207752e0f564f72f8474ccbead4aad798b",
    }),
}
RETIRED_FILE_HASHES = {
    Path("agents/orchestrator-recon.md"): frozenset({
        "18cbce96483f8b1ef7d2a90b2184853cd82af1f1bcd6158a457409f41742dd83",
        "6fdfc984f4e23ab587ebe859214e0c7ecac26bf330009f8faf9cd29c72d65625",
        "7264840d5622061486cc39275b14f9bcda96febbaa4009a7ae49ac28a336ae3a",
        "cb79e48a24d199614e6f45e232630a59b17e43738f91ef792ec496f5887cb4e6",
        "d3ced39fa05b99203950ae2bf48aee8abaaecf2971df73e332973a4e8240f900",
        "1a0b6c87512fbf79ea77cd139ba6fd7d55d75227159259396980670cf7792e57",
        "b7f55885c03cdbc268556b4911c3b53fd3815da0e1e55107e67e98afdd3ea41e",
        "65b7ca216b9890b276e756c2e48a1ac052f9c4e495bcf56b528adeca2b07ae33",
    }),
}
GLOBAL_INSTRUCTIONS_FILE = "AGENTS.md"
GLOBAL_INSTRUCTIONS_START = "<!-- opencode-agents: caveman:start -->"
GLOBAL_INSTRUCTIONS_END = "<!-- opencode-agents: caveman:end -->"


def global_instructions(newline: str = "\n") -> bytes:
    return f"{GLOBAL_INSTRUCTIONS_START}{newline}When `caveman` skill is installed, load it and use it for concise technically complete responses. If skill is unavailable, continue normally.{newline}{GLOBAL_INSTRUCTIONS_END}{newline}".encode()


def default_target() -> Path:
    configured = os.environ.get("OPENCODE_CONFIG_DIR")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data) / "opencode"
    return Path.home() / ".config" / "opencode"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Install and update OpenCode agents and plugins.")
    result.add_argument("command", choices=("install", "update", "status"))
    result.add_argument("--source", type=Path, help="Use a local source directory instead of GitHub API.")
    result.add_argument("--repository", default=None, help="GitHub repository URL or owner/name.")
    result.add_argument("--ref", default=None, help="Git branch, tag, or commit to fetch from GitHub.")
    result.add_argument("--github-api", default=DEFAULT_GITHUB_API, help=argparse.SUPPRESS)
    result.add_argument("--target", type=Path, default=default_target())
    result.add_argument("--backup-dir", type=Path)
    result.add_argument("--dry-run", action="store_true")
    return result


def source_files(source: Path, target: Path):
    files = []
    for group in GROUPS:
        source_group = source / group
        if not source_group.is_dir():
            raise RuntimeError(f"source missing {group}/: {source}")
        for source_file in sorted(source_group.glob(GROUP_PATTERNS[group])):
            files.append((source_file, target / group / source_file.relative_to(source_group)))
    yield from sorted(files, key=lambda item: str(item[1]))


def repository_name(repository: str) -> str:
    value = repository.strip()
    if "://" not in value:
        value = f"https://github.com/{value}"
    parsed = urlparse(value)
    if parsed.scheme.lower() != "https" or parsed.netloc.lower() != "github.com":
        raise RuntimeError(f"unsupported repository URL: {repository}")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise RuntimeError(f"invalid GitHub repository: {repository}")
    return f"{parts[0]}/{parts[1].removesuffix('.git')}"


def installable_repository_path(value: str) -> bool:
    if value == "AGENTS.md":
        return True
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 2:
        return False
    group, name = relative.parts
    return group in GROUP_PATTERNS and Path(name).match(GROUP_PATTERNS[group])


class SameHostRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        current = urlparse(req.full_url)
        destination = urlparse(newurl)
        if current.netloc.lower() != destination.netloc.lower() or destination.scheme.lower() != "https":
            raise URLError("refusing unsafe GitHub API redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def github_json(url: str, token: Optional[str]) -> dict:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise RuntimeError("GitHub API URL must use HTTPS")
    if token and parsed.netloc.lower() != "api.github.com":
        raise RuntimeError("GITHUB_TOKEN may only be sent to api.github.com")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "opencode-agents"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        opener = build_opener(SameHostRedirectHandler)
        with opener.open(Request(url, headers=headers), timeout=30) as response:
            content = response.read(MAX_GITHUB_RESPONSE_BYTES + 1)
            if len(content) > MAX_GITHUB_RESPONSE_BYTES:
                raise RuntimeError(f"GitHub API response is too large: {url}")
            return json.loads(content)
    except HTTPError as error:
        raise RuntimeError(f"GitHub API request failed ({error.code}): {url}") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"GitHub API request failed: {url}: {error}") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError(f"GitHub API returned invalid JSON: {url}") from error


@contextmanager
def prepared_source(source: Optional[Path], repository: Optional[str], ref: str, api_url: str):
    if source is not None:
        yield source.expanduser().resolve()
        return
    script_path = globals().get("__file__")
    local_source = Path(script_path).resolve().parent if repository is None and ref is None and script_path and Path(script_path).is_file() else None
    if local_source is not None:
        yield local_source
        return
    remote = repository or DEFAULT_REPOSITORY
    repo = repository_name(remote)
    token = os.environ.get("GITHUB_TOKEN")
    selected_ref = ref or github_json(f"{api_url.rstrip('/')}/repos/{repo}", token).get("default_branch")
    if not selected_ref:
        raise RuntimeError(f"GitHub repository has no default branch: {repo}")
    tree_url = f"{api_url.rstrip('/')}/repos/{repo}/git/trees/{quote(selected_ref, safe='')}?recursive=1"
    tree = github_json(tree_url, token)
    if tree.get("truncated"):
        raise RuntimeError("GitHub repository tree is truncated; use a narrower ref")
    with tempfile.TemporaryDirectory(prefix="opencode-agents-") as temporary:
        root = Path(temporary)
        entries = []
        seen_paths = set()
        for entry in tree.get("tree", []):
            path = entry.get("path", "")
            if entry.get("type") != "blob" or not installable_repository_path(path):
                continue
            if path in seen_paths:
                raise RuntimeError(f"duplicate path from GitHub API: {path}")
            if isinstance(entry.get("size"), int) and entry["size"] > MAX_SOURCE_FILE_BYTES:
                raise RuntimeError(f"GitHub source file is too large: {path}")
            seen_paths.add(path)
            entries.append(entry)
        if len(entries) > MAX_SOURCE_FILES:
            raise RuntimeError(f"GitHub source contains too many installable files: {len(entries)}")
        declared_total = sum(entry.get("size", 0) for entry in entries if isinstance(entry.get("size"), int))
        if declared_total > MAX_SOURCE_TOTAL_BYTES:
            raise RuntimeError(f"GitHub source is too large: {declared_total} bytes")
        if not entries:
            raise RuntimeError(f"GitHub repository contains no installable files: {repo}@{selected_ref}")
        decoded_total = 0
        for entry in entries:
            relative = Path(entry["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"unsafe path from GitHub API: {entry['path']}")
            content = github_json(f"{api_url.rstrip('/')}/repos/{repo}/git/blobs/{entry['sha']}", token)
            try:
                encoded = content["content"]
                if len(encoded) > MAX_SOURCE_FILE_BYTES * 2:
                    raise RuntimeError(f"GitHub source file is too large: {entry['path']}")
                decoded = base64.b64decode(encoded, validate=False)
            except (KeyError, ValueError) as error:
                raise RuntimeError(f"invalid blob response for {entry['path']}") from error
            if len(decoded) > MAX_SOURCE_FILE_BYTES:
                raise RuntimeError(f"GitHub source file is too large: {entry['path']}")
            decoded_total += len(decoded)
            if decoded_total > MAX_SOURCE_TOTAL_BYTES:
                raise RuntimeError(f"GitHub source is too large: {decoded_total} bytes")
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(decoded)
        yield root


def global_instructions_path(target: Path) -> Path:
    return target / GLOBAL_INSTRUCTIONS_FILE


def source_metadata_file(source: Path) -> Path:
    instructions = source / GLOBAL_INSTRUCTIONS_FILE
    if instructions.exists():
        return instructions
    for group in GROUPS:
        files = sorted((source / group).glob(GROUP_PATTERNS[group]))
        if files:
            return files[0]
    raise RuntimeError(f"source contains no files for metadata: {source}")


def print_caveman_next_step() -> None:
    print("next: install official Caveman integration")
    print("npx -y github:JuliusBrussee/caveman -- --only opencode")
    print("https://github.com/JuliusBrussee/caveman")


def rendered_global_instructions(target: Path) -> bytes:
    path = global_instructions_path(target)
    if not path.exists():
        return global_instructions()
    content = path.read_bytes()
    newline = "\r\n" if b"\r\n" in content else "\n"
    guidance = global_instructions(newline)
    start = content.find(GLOBAL_INSTRUCTIONS_START.encode())
    end_marker = GLOBAL_INSTRUCTIONS_END.encode()
    if start < 0:
        separator = b"" if not content or content.endswith((b"\n", b"\r")) else b"\n"
        if separator and newline == "\r\n":
            separator = b"\r\n"
        return content + separator + guidance
    end = content.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"global instructions contain incomplete caveman block: {path}")
    end += len(end_marker)
    if end < len(content) and content[end:end + 2] == b"\r\n":
        end += 2
    elif end < len(content) and content[end:end + 1] == b"\n":
        end += 1
    prefix = content[:start]
    suffix = content[end:]
    return prefix + guidance + suffix


def rendered_content(source: Path, target: Path, target_file: Path) -> bytes:
    return source.read_bytes()


def validate_target_group(path: Path) -> None:
    if is_link_or_reparse(path) or (path.exists() and not path.is_dir()):
        raise RuntimeError(f"target group is not a directory: {path}")


def validate_target_file(path: Path) -> None:
    if is_link_or_reparse(path):
        raise RuntimeError(f"refusing symlink target: {path}")
    if path.exists() and not path.is_file():
        raise RuntimeError(f"target is not a regular file: {path}")


def atomic_copy(source: Path, target: Path) -> None:
    atomic_write(source, source.read_bytes(), target)


def secure_parent_directory(path: Path):
    if os.name != "posix":
        return None
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    absolute = Path(os.path.abspath(path))
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            try:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(part, dir_fd=descriptor)
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def safe_remove(target: Path) -> None:
    descriptor = secure_parent_directory(target.parent)
    if descriptor is None:
        target.unlink(missing_ok=True)
        return
    try:
        os.unlink(target.name, dir_fd=descriptor)
    except FileNotFoundError:
        pass
    finally:
        os.close(descriptor)


def atomic_write(source: Path, content: bytes, target: Path) -> None:
    descriptor = secure_parent_directory(target.parent)
    if descriptor is None:
        atomic_write_path(source, content, target)
        return
    temporary_name = f".{target.name}.{uuid.uuid4().hex}"
    mode = stat.S_IMODE(source.stat().st_mode)
    temporary_descriptor = os.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=descriptor)
    try:
        with os.fdopen(temporary_descriptor, "wb") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target.name, src_dir_fd=descriptor, dst_dir_fd=descriptor)
    finally:
        try:
            os.unlink(temporary_name, dir_fd=descriptor)
        except FileNotFoundError:
            pass
        os.close(descriptor)


def atomic_write_path(source: Path, content: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", delete=False)
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        with temporary_path.open("wb") as output:
            output.write(content)
        shutil.copymode(source, temporary_path)
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)


def backup_copy(source: Path, target: Path) -> None:
    current = target
    while True:
        if is_link_or_reparse(current):
            raise RuntimeError(f"refusing symlink backup path: {current}")
        if current.parent == current:
            break
        current = current.parent
    atomic_copy(source, target)


def reject_symlink_components(path: Path, description: str) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if is_link_or_reparse(current):
            raise RuntimeError(f"refusing symlink {description}: {current}")


def is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def validate_backup(backup: Path, source: Path, target: Path) -> Path:
    backup = backup.expanduser()
    reject_symlink_components(backup, "backup path")
    backup = backup.resolve()
    if backup == source or backup == target or source in backup.parents or target in backup.parents or backup in source.parents or backup in target.parents:
        raise RuntimeError(f"backup path overlaps source or target: {backup}")
    if is_link_or_reparse(backup) or (backup.exists() and not backup.is_dir()):
        raise RuntimeError(f"backup path is not a directory: {backup}")
    return backup


def validate_target(target: Path) -> None:
    if is_link_or_reparse(target):
        raise RuntimeError(f"refusing symlink target root: {target}")
    for group in GROUPS:
        validate_target_group(target / group)


def validate_global_instructions(path: Path) -> None:
    validate_target_file(path)


def status(source: Path, target: Path) -> None:
    validate_target(target)
    counts = {"missing": 0, "changed": 0, "current": 0, "retired": 0}
    files = list(source_files(source, target))
    for source_file, target_file in files:
        validate_target_file(target_file)
        relative = target_file.relative_to(target)
        if not target_file.exists():
            state = "missing"
        elif rendered_content(source_file, target, target_file) == target_file.read_bytes():
            state = "current"
        else:
            state = "changed"
        counts[state] += 1
        print(f"{state} {relative}")
    for relative, known_hashes in RETIRED_FILE_HASHES.items():
        target_file = target / relative
        validate_target_file(target_file)
        if target_file.exists() and hashlib.sha256(target_file.read_bytes()).hexdigest() in known_hashes:
            counts["retired"] += 1
            print(f"retired {relative}")
    instructions = global_instructions_path(target)
    validate_global_instructions(instructions)
    if not instructions.exists():
        state = "missing"
    elif rendered_global_instructions(target) == instructions.read_bytes():
        state = "current"
    else:
        state = "changed"
    counts[state] += 1
    print(f"{state} {GLOBAL_INSTRUCTIONS_FILE} (caveman guidance)")
    print("summary " + " ".join(f"{key}={counts[key]}" for key in counts))


def install(source: Path, target: Path, dry_run: bool) -> None:
    validate_target(target)
    files = list(source_files(source, target))
    metadata_file = source_metadata_file(source)
    for _, target_file in files:
        validate_target_file(target_file)
    instructions = global_instructions_path(target)
    validate_global_instructions(instructions)
    rendered_instructions = rendered_global_instructions(target)
    rendered_files = [(source_file, target_file, rendered_content(source_file, target, target_file)) for source_file, target_file in files]
    installed = 0
    skipped = 0
    added_files = []
    previous_instructions = instructions.read_bytes() if instructions.exists() else None
    instructions_changed = previous_instructions != rendered_instructions
    try:
        for source_file, target_file, content in rendered_files:
            relative = target_file.relative_to(target)
            if target_file.exists():
                print(f"skip {relative}")
                skipped += 1
            else:
                print(f"copy {source_file} -> {target_file}" if dry_run else f"install {relative}")
                if not dry_run:
                    atomic_write(source_file, content, target_file)
                    added_files.append(target_file)
                installed += 1
        if not instructions_changed:
            print(f"skip {GLOBAL_INSTRUCTIONS_FILE} (caveman guidance)")
            skipped += 1
        else:
            print(f"copy global caveman guidance -> {instructions}" if dry_run else f"install {GLOBAL_INSTRUCTIONS_FILE} (caveman guidance)")
            if not dry_run:
                atomic_write(metadata_file, rendered_instructions, instructions)
            installed += 1
    except (OSError, RuntimeError) as error:
        if not dry_run:
            rollback_errors = []
            for target_file in reversed(added_files):
                try:
                    safe_remove(target_file)
                except OSError as rollback_error:
                    rollback_errors.append(str(rollback_error))
            if instructions_changed:
                try:
                    if previous_instructions is None:
                        safe_remove(instructions)
                    else:
                        atomic_write(metadata_file, previous_instructions, instructions)
                except (OSError, RuntimeError) as rollback_error:
                    rollback_errors.append(str(rollback_error))
            if rollback_errors:
                raise RuntimeError(f"{error}; rollback failed: {'; '.join(rollback_errors)}") from error
        raise
    print(f"summary installed={installed} skipped={skipped}")
    print_caveman_next_step()


def update(source: Path, target: Path, backup: Optional[Path], dry_run: bool) -> None:
    validate_target(target)
    files = list(source_files(source, target))
    metadata_file = source_metadata_file(source)
    if backup is None:
        backup = target.parent / f"opencode-agents-backup-{datetime.now():%Y%m%d-%H%M%S-%f}"
    backup = validate_backup(backup, source, target)
    counts = {"updated": 0, "added": 0, "removed": 0, "unchanged": 0, "backup": 0}
    updated_files = []
    added_files = []
    removed_files = []
    try:
        for source_file, target_file in files:
            validate_target_file(target_file)
            relative = target_file.relative_to(target)
            if target_file.exists() and rendered_content(source_file, target, target_file) == target_file.read_bytes():
                print(f"current {relative}")
                counts["unchanged"] += 1
            elif target_file.exists():
                known_hashes = OWNED_PREVIOUS_FILE_HASHES.get(relative)
                if known_hashes is not None and hashlib.sha256(target_file.read_bytes()).hexdigest() not in known_hashes:
                    print(f"preserve user-owned {relative}")
                    continue
                print(f"update {relative}")
                if not dry_run:
                    backup_file = backup / relative
                    backup_copy(target_file, backup_file)
                    updated_files.append((target_file, backup_file))
                    atomic_write(source_file, rendered_content(source_file, target, target_file), target_file)
                counts["backup"] += 1
                counts["updated"] += 1
            else:
                print(f"add {relative}")
                if not dry_run:
                    added_files.append(target_file)
                    atomic_write(source_file, rendered_content(source_file, target, target_file), target_file)
                counts["added"] += 1
        for relative, known_hashes in RETIRED_FILE_HASHES.items():
            target_file = target / relative
            validate_target_file(target_file)
            if not target_file.exists():
                continue
            if hashlib.sha256(target_file.read_bytes()).hexdigest() not in known_hashes:
                print(f"preserve user-owned {relative}")
                continue
            print(f"remove {relative}")
            if not dry_run:
                backup_file = backup / relative
                backup_copy(target_file, backup_file)
                removed_files.append((target_file, backup_file))
                safe_remove(target_file)
            counts["backup"] += 1
            counts["removed"] += 1
        instructions = global_instructions_path(target)
        validate_global_instructions(instructions)
        rendered = rendered_global_instructions(target)
        if instructions.exists() and rendered == instructions.read_bytes():
            print(f"current {GLOBAL_INSTRUCTIONS_FILE} (caveman guidance)")
            counts["unchanged"] += 1
        elif instructions.exists():
            print(f"update {GLOBAL_INSTRUCTIONS_FILE} (caveman guidance)")
            if not dry_run:
                backup_file = backup / GLOBAL_INSTRUCTIONS_FILE
                backup_copy(instructions, backup_file)
                updated_files.append((instructions, backup_file))
                atomic_write(metadata_file, rendered, instructions)
            counts["backup"] += 1
            counts["updated"] += 1
        else:
            print(f"add {GLOBAL_INSTRUCTIONS_FILE} (caveman guidance)")
            if not dry_run:
                added_files.append(instructions)
                atomic_write(metadata_file, rendered, instructions)
            counts["added"] += 1
    except (OSError, RuntimeError) as error:
        if not dry_run:
            rollback_errors = []
            for target_file, backup_file in reversed(updated_files):
                try:
                    atomic_copy(backup_file, target_file)
                except (OSError, RuntimeError) as rollback_error:
                    rollback_errors.append(str(rollback_error))
            for target_file in reversed(added_files):
                try:
                    safe_remove(target_file)
                except OSError as rollback_error:
                    rollback_errors.append(str(rollback_error))
            for target_file, backup_file in reversed(removed_files):
                try:
                    atomic_copy(backup_file, target_file)
                except (OSError, RuntimeError) as rollback_error:
                    rollback_errors.append(str(rollback_error))
            if rollback_errors:
                raise RuntimeError(f"{error}; rollback failed: {'; '.join(rollback_errors)}") from error
        raise
    backup_text = "not-created" if dry_run else str(backup)
    print(f"summary updated={counts['updated']} added={counts['added']} removed={counts['removed']} unchanged={counts['unchanged']} backup={backup_text} files={counts['backup']}")
    print_caveman_next_step()


def main() -> int:
    arguments = parser().parse_args()
    expanded_target = arguments.target.expanduser()
    target = expanded_target.resolve()
    try:
        reject_symlink_components(expanded_target, "target path")
        with prepared_source(arguments.source, arguments.repository, arguments.ref, arguments.github_api) as source:
            if arguments.command == "status":
                if arguments.dry_run:
                    raise RuntimeError("--dry-run cannot be used with status")
                status(source, target)
            elif arguments.command == "install":
                install(source, target, arguments.dry_run)
            else:
                update(source, target, arguments.backup_dir.expanduser() if arguments.backup_dir else None, arguments.dry_run)
    except (OSError, RuntimeError) as error:
        print(f"opencode-agents: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
