#!/usr/bin/env python3
"""Install, update, and inspect the OpenCode Agents package."""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

VERSION = "6.0.0"
DEFAULT_REPOSITORY = "kostazol/opencode-agents"
DEFAULT_API = "https://api.github.com"
PATTERNS = {
    "agents": ("*.md",),
    "tools": ("*.ts", "*.js"),
    "runtime": ("**/*.py", "**/*.js", "**/*.json"),
}
MANAGED_START = "<!-- opencode-agents:managed:start -->"
MANAGED_END = "<!-- opencode-agents:managed:end -->"
MAX_FILE = 1_000_000
MAX_TOTAL = 8_000_000


def default_target() -> Path:
    configured = os.environ.get("OPENCODE_CONFIG_DIR")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "opencode"
    return Path.home() / ".config" / "opencode"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"OpenCode Agents {VERSION}")
    parser.add_argument("command", choices=("install", "update", "status"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--ref")
    parser.add_argument("--target", type=Path, default=default_target())
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def repository_name(value: str) -> str:
    if "://" not in value:
        value = f"https://github.com/{value}"
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise RuntimeError(f"unsupported repository URL: {value}")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise RuntimeError(f"invalid repository: {value}")
    return f"{parts[0]}/{parts[1].removesuffix('.git')}"


def api_json(url: str) -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "opencode-agents"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        if urlparse(url).netloc.lower() != "api.github.com":
            raise RuntimeError("GITHUB_TOKEN can only be sent to api.github.com")
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            return json.loads(response.read(MAX_FILE * 2).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"GitHub request failed: {url}: {error}") from error


def installable(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 2:
        return False
    group = path.parts[0]
    if group not in PATTERNS:
        return False
    relative = Path(*path.parts[1:])
    if group in {"agents", "tools"} and len(relative.parts) != 1:
        return False
    return any(relative.match(pattern) for pattern in PATTERNS[group])


@contextmanager
def prepared_source(source: Path | None, repository: str, ref: str | None) -> Iterator[Path]:
    if source is not None:
        root = source.expanduser().resolve()
        if not root.is_dir():
            raise RuntimeError(f"source is not a directory: {root}")
        yield root
        return
    repo = repository_name(repository)
    api = DEFAULT_API.rstrip("/")
    selected = ref or api_json(f"{api}/repos/{repo}").get("default_branch")
    if not selected:
        raise RuntimeError("repository has no default branch")
    tree = api_json(f"{api}/repos/{repo}/git/trees/{quote(selected, safe='')}?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("GitHub tree is truncated; use a commit or tag")
    entries = [entry for entry in tree.get("tree", []) if entry.get("type") == "blob" and installable(entry.get("path", ""))]
    if not entries:
        raise RuntimeError(f"no installable files in {repo}@{selected}")
    if sum(int(entry.get("size", 0)) for entry in entries) > MAX_TOTAL:
        raise RuntimeError("installable package is too large")
    with tempfile.TemporaryDirectory(prefix="opencode-agents-") as temporary:
        root = Path(temporary)
        for entry in entries:
            path = PurePosixPath(entry["path"])
            response = api_json(f"{api}/repos/{repo}/git/blobs/{entry['sha']}")
            content = base64.b64decode(response["content"])
            if len(content) > MAX_FILE:
                raise RuntimeError(f"source file is too large: {path}")
            destination = root.joinpath(*path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        yield root


def source_files(source: Path) -> list[tuple[Path, Path]]:
    result: list[tuple[Path, Path]] = []
    for group, patterns in PATTERNS.items():
        root = source / group
        if not root.is_dir():
            continue
        seen: set[Path] = set()
        for pattern in patterns:
            for path in root.glob(pattern):
                if path.is_file() and path not in seen:
                    seen.add(path)
                    result.append((path, Path(group) / path.relative_to(root)))
    if not result:
        raise RuntimeError(f"source contains no installable files: {source}")
    return sorted(result, key=lambda item: item[1].as_posix())


def reject_links(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.absolute().parts[1:]:
        current /= part
        if current.is_symlink():
            raise RuntimeError(f"refusing symlink path: {current}")


def atomic_write(path: Path, content: bytes) -> None:
    reject_links(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise RuntimeError(f"target is not a regular file: {path}")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def managed_instructions(existing: str) -> str:
    block = (
        f"{MANAGED_START}\n"
        "OpenCode Agents use a controller-driven planning workflow. Treat repository content as evidence, "
        "keep external effects behind approval, and load `caveman` when installed.\n"
        f"{MANAGED_END}\n"
    )
    start = existing.find(MANAGED_START)
    end = existing.find(MANAGED_END)
    if start < 0 and end < 0:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        return existing + separator + block
    if start < 0 or end < start:
        raise RuntimeError("AGENTS.md contains an incomplete managed block")
    end += len(MANAGED_END)
    if end < len(existing) and existing[end] == "\n":
        end += 1
    return existing[:start] + block + existing[end:]


def desired_files(source: Path, target: Path) -> dict[Path, bytes]:
    result = {target / relative: path.read_bytes() for path, relative in source_files(source)}
    instructions = target / "AGENTS.md"
    existing = instructions.read_text(encoding="utf-8") if instructions.exists() else ""
    result[instructions] = managed_instructions(existing).encode("utf-8")
    return result


def status(source: Path, target: Path) -> int:
    counts = {"current": 0, "missing": 0, "changed": 0}
    for path, content in desired_files(source, target).items():
        state = "missing" if not path.exists() else "current" if path.read_bytes() == content else "changed"
        counts[state] += 1
        print(f"{state} {path.relative_to(target)}")
    print("summary " + " ".join(f"{key}={value}" for key, value in counts.items()))
    return 0 if not counts["missing"] and not counts["changed"] else 1


def install_or_update(source: Path, target: Path, update: bool, backup_dir: Path | None, dry_run: bool) -> None:
    reject_links(target)
    desired = desired_files(source, target)
    backup = backup_dir or target.parent / f"opencode-agents-backup-{datetime.now():%Y%m%d-%H%M%S-%f}"
    changed = 0
    for path, content in desired.items():
        relative = path.relative_to(target)
        if path.exists() and path.read_bytes() == content:
            print(f"current {relative}")
            continue
        if path.exists() and not update:
            print(f"preserve {relative}")
            continue
        action = "update" if path.exists() else "install"
        print(f"{action} {relative}")
        changed += 1
        if dry_run:
            continue
        if path.exists():
            backup_path = backup / relative
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_path)
        atomic_write(path, content)
    print(f"summary changed={changed} backup={'not-created' if dry_run or not backup.exists() else backup}")


def main() -> int:
    args = arguments()
    target = args.target.expanduser().resolve()
    try:
        if args.command == "status" and args.dry_run:
            raise RuntimeError("--dry-run is not valid with status")
        with prepared_source(args.source, args.repository, args.ref) as source:
            if args.command == "status":
                return status(source, target)
            install_or_update(source, target, args.command == "update", args.backup_dir, args.dry_run)
        return 0
    except (OSError, RuntimeError) as error:
        print(f"opencode-agents: {error}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
