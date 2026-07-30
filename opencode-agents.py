#!/usr/bin/env python3
"""Install and update OpenCode agents and shared protocols."""

from __future__ import annotations

import argparse
from datetime import datetime
import os
import shutil
import stat
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional


VERSION = "2.1.0"
GROUPS = ("agents", "protocols")
LEGACY_AGENT_FILES = (
    "Atlas - Plan Executor.md",
    "Hephaestus - Deep Agent.md",
    "Metis - Plan Consultant.md",
    "Prometheus - Plan Builder.md",
    "Sisyphus-Junior.md",
    "bootstrapper.md",
    "build-caveman-hardcode.md",
    "build-caveman.md",
    "build.md",
    "cavecrew-builder.md",
    "cavecrew-investigator.md",
    "cavecrew-reviewer.md",
    "explore-caveman-hardcode.md",
    "explore.md",
    "general-caveman-hardcode.md",
    "general.md",
    "md-planner.md",
    "orchestrator-caveman-hardcode.md",
    "plan.md",
    "planner-caveman-hardcode.md",
)


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
    result = argparse.ArgumentParser(description="Install and update OpenCode agents and protocols.")
    result.add_argument("command", choices=("install", "update", "status"))
    result.add_argument("--source", type=Path, default=Path(__file__).resolve().parent)
    result.add_argument("--target", type=Path, default=default_target())
    result.add_argument("--backup-dir", type=Path)
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--prune-legacy", action="store_true", help="Remove only legacy agents formerly shipped by this repository.")
    return result


def source_files(source: Path, target: Path):
    for group in GROUPS:
        source_group = source / group
        if not source_group.is_dir():
            raise RuntimeError(f"source missing {group}/: {source}")
        for source_file in sorted(source_group.glob("*.md")):
            yield source_file, target / group / source_file.name


def rendered_content(source: Path, target: Path) -> bytes:
    content = source.read_bytes()
    if source.parent.name != "agents":
        return content
    protocol_path = str(target / "protocols" / "orchestrator-v2.md")
    yaml_path = protocol_path.replace("'", "''")
    return content.replace(b"__OPENCODE_PROTOCOL_PATH_YAML__", yaml_path.encode()).replace(b"__OPENCODE_PROTOCOL_PATH_TEXT__", protocol_path.encode())


def validate_target_group(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise RuntimeError(f"target group is not a directory: {path}")


def validate_target_file(path: Path) -> None:
    if path.is_symlink():
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
        if current.is_symlink():
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
        if current.is_symlink():
            raise RuntimeError(f"refusing symlink {description}: {current}")


def validate_backup(backup: Path, source: Path, target: Path) -> Path:
    backup = backup.expanduser()
    reject_symlink_components(backup, "backup path")
    backup = backup.resolve()
    if backup == source or backup == target or source in backup.parents or target in backup.parents or backup in source.parents or backup in target.parents:
        raise RuntimeError(f"backup path overlaps source or target: {backup}")
    if backup.is_symlink() or (backup.exists() and not backup.is_dir()):
        raise RuntimeError(f"backup path is not a directory: {backup}")
    return backup


def validate_target(target: Path) -> None:
    if target.is_symlink():
        raise RuntimeError(f"refusing symlink target root: {target}")
    for group in GROUPS:
        validate_target_group(target / group)


def status(source: Path, target: Path) -> None:
    validate_target(target)
    counts = {"missing": 0, "changed": 0, "current": 0}
    for source_file, target_file in source_files(source, target):
        validate_target_file(target_file)
        relative = target_file.relative_to(target)
        if not target_file.exists():
            state = "missing"
        elif rendered_content(source_file, target) == target_file.read_bytes():
            state = "current"
        else:
            state = "changed"
        counts[state] += 1
        print(f"{state} {relative}")
    print("summary " + " ".join(f"{key}={counts[key]}" for key in counts))


def install(source: Path, target: Path, dry_run: bool) -> None:
    validate_target(target)
    installed = 0
    skipped = 0
    for source_file, target_file in source_files(source, target):
        validate_target_file(target_file)
        relative = target_file.relative_to(target)
        if target_file.exists():
            print(f"skip {relative}")
            skipped += 1
        else:
            print(f"copy {source_file} -> {target_file}" if dry_run else f"install {relative}")
            if not dry_run:
                atomic_write(source_file, rendered_content(source_file, target), target_file)
            installed += 1
    print(f"summary installed={installed} skipped={skipped}")


def update(source: Path, target: Path, backup: Optional[Path], dry_run: bool, prune_legacy: bool) -> None:
    validate_target(target)
    if backup is None:
        backup = target.parent / f"opencode-agents-backup-{datetime.now():%Y%m%d-%H%M%S-%f}"
    backup = validate_backup(backup, source, target)
    counts = {"updated": 0, "added": 0, "unchanged": 0, "backup": 0, "pruned": 0}
    updated_files = []
    added_files = []
    try:
        for source_file, target_file in source_files(source, target):
            validate_target_file(target_file)
            relative = target_file.relative_to(target)
            if target_file.exists() and rendered_content(source_file, target) == target_file.read_bytes():
                print(f"current {relative}")
                counts["unchanged"] += 1
            elif target_file.exists():
                print(f"update {relative}")
                if not dry_run:
                    backup_file = backup / relative
                    backup_copy(target_file, backup_file)
                    updated_files.append((target_file, backup_file))
                    atomic_write(source_file, rendered_content(source_file, target), target_file)
                counts["backup"] += 1
                counts["updated"] += 1
            else:
                print(f"add {relative}")
                if not dry_run:
                    added_files.append(target_file)
                    atomic_write(source_file, rendered_content(source_file, target), target_file)
                counts["added"] += 1
        if prune_legacy:
            for file_name in LEGACY_AGENT_FILES:
                target_file = target / "agents" / file_name
                validate_target_file(target_file)
                if not target_file.exists():
                    continue
                print(f"prune agents/{file_name}")
                if not dry_run:
                    backup_file = backup / "agents" / file_name
                    backup_copy(target_file, backup_file)
                    updated_files.append((target_file, backup_file))
                    safe_remove(target_file)
                counts["backup"] += 1
                counts["pruned"] += 1
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
            if rollback_errors:
                raise RuntimeError(f"{error}; rollback failed: {'; '.join(rollback_errors)}") from error
        raise
    backup_text = "not-created" if dry_run else str(backup)
    print(f"summary updated={counts['updated']} added={counts['added']} pruned={counts['pruned']} unchanged={counts['unchanged']} backup={backup_text} files={counts['backup']}")


def main() -> int:
    arguments = parser().parse_args()
    source = arguments.source.expanduser().resolve()
    target = arguments.target.expanduser().resolve()
    try:
        reject_symlink_components(arguments.target.expanduser(), "target path")
        if arguments.command == "status":
            if arguments.dry_run:
                raise RuntimeError("--dry-run cannot be used with status")
            if arguments.prune_legacy:
                raise RuntimeError("--prune-legacy can be used only with update")
            status(source, target)
        elif arguments.command == "install":
            if arguments.prune_legacy:
                raise RuntimeError("--prune-legacy can be used only with update")
            install(source, target, arguments.dry_run)
        else:
            update(source, target, arguments.backup_dir.expanduser() if arguments.backup_dir else None, arguments.dry_run, arguments.prune_legacy)
    except (OSError, RuntimeError) as error:
        print(f"opencode-agents: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
