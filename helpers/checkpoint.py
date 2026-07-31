#!/usr/bin/env python3
"""Create one validated Orchestrator checkpoint commit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from typing import Optional


SCHEMA = "orchestrator-checkpoint-v1"
POINTER_PATH = ".orchestrator/checkpoint-active.json"
SHA_PATTERN = re.compile(r"[0-9a-f]{40,64}")
ID_PATTERN = re.compile(r"[0-9a-f]{64}")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class CheckpointError(RuntimeError):
    pass


def git(root: Path, *arguments: str, input_bytes: Optional[bytes] = None, check: bool = True, index_file: Optional[Path] = None) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment["GIT_LITERAL_PATHSPECS"] = "1"
    if index_file is not None:
        environment["GIT_INDEX_FILE"] = str(index_file)
    result = subprocess.run(["git", *arguments], cwd=root, env=environment, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise CheckpointError(f"git {' '.join(arguments)} failed: {error}")
    return result


def output(root: Path, *arguments: str) -> str:
    return git(root, *arguments).stdout.decode("utf-8", errors="strict").strip()


def output_with_index(root: Path, index_file: Path, *arguments: str) -> str:
    return git(root, *arguments, index_file=index_file).stdout.decode("utf-8", errors="strict").strip()


def canonical_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CheckpointError("declared path must be a nonempty string")
    if "\x00" in value or "\\" in value:
        raise CheckpointError(f"declared path is not canonical POSIX: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(part in ("", ".", "..") for part in path.parts):
        raise CheckpointError(f"declared path is unsafe: {value!r}")
    if path.parts[0] in (".git", ".orchestrator"):
        raise CheckpointError(f"declared path is excluded: {value!r}")
    return value


def string_field(request: dict, name: str) -> str:
    value = request.get(name)
    if not isinstance(value, str) or not value:
        raise CheckpointError(f"missing {name}")
    return value


def id_field(request: dict, name: str) -> str:
    value = string_field(request, name)
    if not ID_PATTERN.fullmatch(value):
        raise CheckpointError(f"invalid {name}")
    return value


def path_set(request: dict, name: str) -> tuple[str, ...]:
    values = request.get(name)
    if not isinstance(values, list):
        raise CheckpointError(f"missing {name}")
    paths = tuple(canonical_path(value) for value in values)
    if len(paths) != len(set(paths)):
        raise CheckpointError(f"duplicate path in {name}")
    return paths


def ensure_no_symlink_components(root: Path, path: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise CheckpointError(f"path escapes workspace: {path}") from error
    current = root
    for part in relative.parts:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        reparse = getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if stat.S_ISLNK(metadata.st_mode) or reparse:
            raise CheckpointError(f"symlink component is not allowed: {current}")


def path_state(root: Path, path: str) -> dict:
    target = root.joinpath(*PurePosixPath(path).parts)
    ensure_no_symlink_components(root, target.parent)
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return {"type": "missing"}
    reparse = getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if reparse:
        raise CheckpointError(f"declared path uses unsupported Windows reparse point: {path}")
    if stat.S_ISREG(metadata.st_mode):
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"type": "file", "mode": stat.S_IMODE(metadata.st_mode), "sha256": digest.hexdigest()}
    if stat.S_ISLNK(metadata.st_mode):
        return {"type": "symlink", "target": os.readlink(target)}
    raise CheckpointError(f"declared path is not a file, symlink, or deletion: {path}")


def expected_states(request: dict, declared_paths: tuple[str, ...]) -> dict[str, dict]:
    states = request.get("declared_path_states")
    if not isinstance(states, dict) or set(states) != set(declared_paths):
        raise CheckpointError("declared_path_states do not match declared_paths")
    result = {}
    for path in declared_paths:
        state = states[path]
        if not isinstance(state, dict) or state.get("type") not in ("file", "symlink", "missing"):
            raise CheckpointError(f"invalid declared state for {path}")
        result[path] = state
    return result


def expected_git_states(request: dict, declared_paths: tuple[str, ...]) -> dict[str, dict]:
    states = request.get("declared_git_states")
    if not isinstance(states, dict) or set(states) != set(declared_paths):
        raise CheckpointError("declared_git_states do not match declared_paths")
    result = {}
    for path in declared_paths:
        state = states[path]
        if not isinstance(state, dict) or state.get("type") not in ("blob", "missing"):
            raise CheckpointError(f"invalid declared Git state for {path}")
        if state["type"] == "blob" and (state.get("mode") not in ("100644", "100755", "120000") or not SHA_PATTERN.fullmatch(str(state.get("oid", "")))):
            raise CheckpointError(f"invalid declared Git blob for {path}")
        result[path] = state
    return result


def git_state(workspace_root: Path, git_root: Path, path: str) -> dict:
    state = path_state(workspace_root, path)
    if state["type"] == "missing":
        return {"type": "missing"}
    workspace_relative = workspace_root.relative_to(git_root)
    prefix = "" if workspace_relative == Path(".") else workspace_relative.as_posix()
    repo_path = f"{prefix}/{path}" if prefix else path
    target = workspace_root.joinpath(*PurePosixPath(path).parts)
    if state["type"] == "symlink":
        content = os.fsencode(state["target"])
        mode = "120000"
        oid = git(git_root, "hash-object", "--stdin", input_bytes=content).stdout.decode().strip()
    else:
        content = target.read_bytes()
        mode = "100755" if state["mode"] & 0o111 else "100644"
        oid = git(git_root, "hash-object", "--stdin", f"--path={repo_path}", "--filters", input_bytes=content).stdout.decode().strip()
    return {"type": "blob", "mode": mode, "oid": oid}


def nul_paths(content: bytes) -> set[str]:
    if not content:
        return set()
    return {item.decode("utf-8", errors="surrogateescape") for item in content.rstrip(b"\x00").split(b"\x00")}


def index_entries(root: Path, index_file: Optional[Path] = None) -> dict[tuple[str, str], bytes]:
    content = git(root, "ls-files", "-s", "-z", index_file=index_file).stdout
    entries = {}
    for record in content.rstrip(b"\x00").split(b"\x00") if content else ():
        metadata, path = record.split(b"\t", 1)
        stage = metadata.rsplit(b" ", 1)[1].decode("ascii")
        entries[(path.decode("utf-8", errors="surrogateescape"), stage)] = metadata
    return entries


def changed_paths(root: Path) -> set[str]:
    changed = nul_paths(git(root, "diff", "--name-only", "-z").stdout)
    changed.update(nul_paths(git(root, "diff", "--cached", "--name-only", "-z").stdout))
    changed.update(nul_paths(git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout))
    return changed


def atomic_json(workspace_root: Path, path: Path, payload: dict) -> None:
    ensure_no_symlink_components(workspace_root, path.parent)
    if path.is_symlink():
        raise CheckpointError(f"refusing symlink output: {path}")
    content = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def process_is_alive(process_id: int) -> bool:
    if process_id <= 0:
        return False
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def recover_orchestrator_index_lock(git_path: Path, expected_head: str, current_head: str, request_id: str) -> None:
    lock_path = git_path.with_name(f"{git_path.name}.lock")
    metadata_path = git_path.with_name(f"{git_path.name}.lock.orchestrator.json")
    if not metadata_path.exists():
        return
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CheckpointError(f"invalid checkpoint index-lock metadata: {error}") from error
    if not isinstance(metadata, dict):
        raise CheckpointError("invalid checkpoint index-lock metadata fields")
    process_id = metadata.get("pid")
    index_sha256 = metadata.get("index_sha256")
    if metadata.get("schema") != "orchestrator-index-lock-v1" or not isinstance(process_id, int) or isinstance(process_id, bool) or process_id <= 0 or not isinstance(index_sha256, str) or not ID_PATTERN.fullmatch(index_sha256):
        raise CheckpointError("invalid checkpoint index-lock metadata fields")
    if metadata.get("request_id") != request_id or metadata.get("expected_head") != expected_head:
        raise CheckpointError("checkpoint index lock belongs to another request")
    if process_id != os.getpid() and process_is_alive(process_id):
        raise CheckpointError("checkpoint index lock is owned by active process")
    if lock_path.exists():
        actual_digest = hashlib.sha256(lock_path.read_bytes()).hexdigest()
        if index_sha256 != actual_digest:
            raise CheckpointError("checkpoint index lock content mismatch")
        if current_head == expected_head:
            lock_path.unlink()
            metadata_path.unlink()
    else:
        metadata_path.unlink()


def request_file(root: Path) -> Path:
    pointer_path = root / POINTER_PATH
    ensure_no_symlink_components(root, pointer_path)
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CheckpointError(f"invalid active checkpoint pointer: {error}") from error
    if not isinstance(pointer, dict):
        raise CheckpointError("invalid active checkpoint pointer")
    if pointer.get("schema") != "orchestrator-checkpoint-pointer-v1":
        raise CheckpointError("unsupported active checkpoint pointer")
    workflow_root = Path(string_field(pointer, "workflow_root"))
    request_relative = PurePosixPath(string_field(pointer, "request"))
    if request_relative.is_absolute() or ".." in request_relative.parts:
        raise CheckpointError("unsafe active checkpoint request path")
    request_path = workflow_root.joinpath(*request_relative.parts)
    ensure_no_symlink_components(root, request_path)
    expected_parent = workflow_root / "snapshots" / "checkpoint-requests"
    if request_path.parent != expected_parent:
        raise CheckpointError("active checkpoint request path mismatch")
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CheckpointError(f"invalid checkpoint request {request_path}: {error}") from error
    if not isinstance(request, dict):
        raise CheckpointError("invalid checkpoint request")
    if request.get("state") not in ("READY", "COMPLETED"):
        raise CheckpointError("active checkpoint request is not actionable")
    return request_path


def index_digest(entries: dict[tuple[str, str], bytes], excluded_paths: set[str]) -> str:
    digest = hashlib.sha256()
    for path, stage in sorted(key for key in entries if key[0] not in excluded_paths):
        digest.update(os.fsencode(path))
        digest.update(b"\x00")
        digest.update(stage.encode("ascii"))
        digest.update(b"\x00")
        digest.update(entries[(path, stage)])
        digest.update(b"\x00")
    return digest.hexdigest()


def verify_states(workspace_root: Path, states: dict[str, dict]) -> None:
    for path, expected in states.items():
        actual = path_state(workspace_root, path)
        if actual != expected:
            raise CheckpointError(f"reviewed path state changed: {path}")


def verify_index_git_states(entries: dict[tuple[str, str], bytes], repo_paths: tuple[str, ...], workspace_paths: tuple[str, ...], expected: dict[str, dict]) -> None:
    for repo_path, workspace_path in zip(repo_paths, workspace_paths):
        state = expected[workspace_path]
        matching_entries = [entry for (path, _), entry in entries.items() if path == repo_path]
        entry = entries.get((repo_path, "0"))
        if state["type"] == "missing":
            if matching_entries:
                raise CheckpointError(f"deleted path remains staged: {workspace_path}")
            continue
        if entry is None or len(matching_entries) != 1:
            raise CheckpointError(f"declared path is not staged: {workspace_path}")
        parts = entry.decode("ascii").split()
        if len(parts) != 3 or parts[0] != state["mode"] or parts[1] != state["oid"] or parts[2] != "0":
            raise CheckpointError(f"staged Git object differs from review: {workspace_path}")


def verify_commit_git_states(git_root: Path, commit_id: str, repo_paths: tuple[str, ...], workspace_paths: tuple[str, ...], expected: dict[str, dict]) -> None:
    for repo_path, workspace_path in zip(repo_paths, workspace_paths):
        state = expected[workspace_path]
        tree = git(git_root, "ls-tree", "-z", commit_id, "--", repo_path).stdout.rstrip(b"\x00")
        if state["type"] == "missing":
            if tree:
                raise CheckpointError(f"deleted path exists in checkpoint: {workspace_path}")
            continue
        if not tree:
            raise CheckpointError(f"checkpoint omitted path: {workspace_path}")
        metadata, actual_path = tree.split(b"\t", 1)
        parts = metadata.decode("ascii").split()
        if actual_path.decode("utf-8", errors="surrogateescape") != repo_path or len(parts) != 3 or parts[0] != state["mode"] or parts[2] != state["oid"]:
            raise CheckpointError(f"checkpoint Git object differs from review: {workspace_path}")


def checkpoint_payload(request: dict, commit_id: str, tree_id: str, expected_head: str, expected_ref: str, declared_paths: tuple[str, ...]) -> dict:
    payload = {
        "schema": SCHEMA,
        "stage": request["stage"],
        "purpose": request["purpose"],
        "repair_id": request.get("repair_id", "none"),
        "commit": commit_id,
        "tree": tree_id,
        "parent": expected_head,
        "branch_ref": expected_ref,
        "declared_paths": list(declared_paths),
        "declared_path_states": request["declared_path_states"],
        "declared_git_states": request["declared_git_states"],
        "product_snapshot_id": request["product_snapshot_id"],
        "review_epoch_id": request["review_epoch_id"],
        "plan_structure_id": request["plan_structure_id"],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["checkpoint_commit_id"] = hashlib.sha256(canonical).hexdigest()
    return payload


def checkpoint(root: Path) -> dict:
    request_path = request_file(root)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(request, dict):
        raise CheckpointError("invalid checkpoint request")
    if request.get("schema") != SCHEMA:
        raise CheckpointError("unsupported checkpoint schema")
    workspace_root = Path(string_field(request, "workspace_root"))
    workflow_root = Path(string_field(request, "workflow_root"))
    if workspace_root != root or not workspace_root.is_absolute():
        raise CheckpointError("workspace root mismatch")
    expected_workflow_root = root / ".orchestrator" / "tasks" / workflow_root.name
    request_directory = workflow_root / "snapshots" / "checkpoint-requests"
    if workflow_root != expected_workflow_root or request_path.parent != request_directory or not TOKEN_PATTERN.fullmatch(request_path.stem):
        raise CheckpointError("workflow root mismatch")
    if string_field(request, "checkpoint_request_id") != request_path.stem:
        raise CheckpointError("checkpoint request ID/path mismatch")
    ensure_no_symlink_components(root, workflow_root)
    git_root = Path(string_field(request, "git_repository_root"))
    if not git_root.is_absolute() or git_root.resolve() != git_root:
        raise CheckpointError("invalid Git repository root")
    try:
        workspace_relative = workspace_root.relative_to(git_root)
    except ValueError as error:
        raise CheckpointError("Git repository root does not contain workspace") from error
    workspace_prefix = "" if workspace_relative == Path(".") else workspace_relative.as_posix()
    expected_head = string_field(request, "expected_head")
    if not SHA_PATTERN.fullmatch(expected_head):
        raise CheckpointError("invalid expected_head")
    expected_ref = string_field(request, "expected_branch_ref")
    if not expected_ref.startswith("refs/heads/"):
        raise CheckpointError("checkpoint requires a branch ref")
    declared_paths = path_set(request, "declared_paths")
    if not declared_paths:
        raise CheckpointError("checkpoint has no declared paths")
    declared_states = expected_states(request, declared_paths)
    declared_git_states = expected_git_states(request, declared_paths)
    declared_repo_paths = tuple(f"{workspace_prefix}/{path}" if workspace_prefix else path for path in declared_paths)
    baseline_user_paths = set(path_set(request, "baseline_user_paths"))
    if baseline_user_paths.intersection(declared_repo_paths):
        raise CheckpointError("declared paths overlap baseline user paths")
    product_snapshot_id = id_field(request, "product_snapshot_id")
    review_epoch_id = id_field(request, "review_epoch_id")
    plan_structure_id = id_field(request, "plan_structure_id")
    stage = string_field(request, "stage")
    if not TOKEN_PATTERN.fullmatch(stage):
        raise CheckpointError("invalid stage")
    subject = string_field(request, "subject")
    if "\n" in subject or "\r" in subject:
        raise CheckpointError("subject must be one line")
    purpose = string_field(request, "purpose")
    if purpose not in ("STAGE", "FINAL_REPAIR"):
        raise CheckpointError("invalid checkpoint purpose")
    repair_id = request.get("repair_id", "none")
    if repair_id != "none" and (not isinstance(repair_id, str) or not TOKEN_PATTERN.fullmatch(repair_id)):
        raise CheckpointError("invalid repair_id")
    if purpose == "FINAL_REPAIR" and repair_id == "none":
        raise CheckpointError("final repair checkpoint requires repair_id")
    reported_git_root = Path(output(git_root, "rev-parse", "--show-toplevel")).resolve()
    if reported_git_root != git_root:
        raise CheckpointError("Git repository root mismatch")
    symbolic_ref = git(git_root, "symbolic-ref", "-q", "HEAD", check=False)
    if symbolic_ref.returncode != 0 or symbolic_ref.stdout.decode().strip() != expected_ref:
        raise CheckpointError("branch changed or HEAD is detached")
    verify_states(workspace_root, declared_states)
    current_head = output(git_root, "rev-parse", "HEAD")
    git_path = Path(output(git_root, "rev-parse", "--git-path", "index"))
    if not git_path.is_absolute():
        git_path = git_root / git_path
    lock_path = git_path.with_name(f"{git_path.name}.lock")
    lock_metadata_path = git_path.with_name(f"{git_path.name}.lock.orchestrator.json")
    recover_orchestrator_index_lock(git_path, expected_head, current_head, request_path.stem)
    allowed_changes = set(declared_repo_paths).union(baseline_user_paths)
    current_changes = changed_paths(git_root)
    unexpected_changes = current_changes.difference(allowed_changes)
    if unexpected_changes:
        raise CheckpointError(f"unexpected changed paths: {sorted(unexpected_changes)!r}")
    workflow_changes = current_changes.difference(baseline_user_paths)
    already_committed = current_head != expected_head
    if not already_committed and workflow_changes != set(declared_repo_paths):
        raise CheckpointError(f"declared path inventory mismatch: {sorted(workflow_changes)!r}")
    if already_committed and workflow_changes.intersection(declared_repo_paths) and not lock_path.exists():
        raise CheckpointError("checkpoint commit exists but workflow paths are dirty")
    before_index = index_entries(git_root)
    reviewed_index_digest = string_field(request, "reviewed_index_digest")
    if not ID_PATTERN.fullmatch(reviewed_index_digest) or (not already_committed and index_digest(before_index, set()) != reviewed_index_digest):
        raise CheckpointError("repository index changed after review")
    prior_index_digest = request.get("pre_user_index_digest")
    current_index_digest = index_digest(before_index, set(declared_repo_paths))
    if prior_index_digest is None:
        if already_committed:
            raise CheckpointError("checkpoint advanced without recovery index evidence")
        request["pre_user_index_digest"] = current_index_digest
        atomic_json(workspace_root, request_path, request)
        prior_index_digest = current_index_digest
    elif prior_index_digest != current_index_digest:
        raise CheckpointError("user index changed before checkpoint")
    original_index = git_path.read_bytes() if git_path.exists() else None
    path_input = b"".join(os.fsencode(path) + b"\x00" for path in declared_repo_paths)
    committed = False
    if not already_committed:
        descriptor, temporary_index_name = tempfile.mkstemp(prefix=".checkpoint-index-", dir=workflow_root / "snapshots")
        os.close(descriptor)
        temporary_index = Path(temporary_index_name)
        temporary_index.unlink()
        try:
            git(git_root, "read-tree", expected_head, index_file=temporary_index)
            git(git_root, "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul", input_bytes=path_input, index_file=temporary_index)
            staged_index = index_entries(git_root, temporary_index)
            verify_index_git_states(staged_index, declared_repo_paths, declared_paths, declared_git_states)
            tree_id = output_with_index(git_root, temporary_index, "write-tree")
            message = f"{subject}\n\nWorkflow-ID: {workflow_root.name}\nStage-ID: {stage}\nProduct-Snapshot-ID: {product_snapshot_id}\nReview-Epoch-ID: {review_epoch_id}\nPlan-Structure-ID: {plan_structure_id}"
            try:
                git(git_root, "var", "GIT_AUTHOR_IDENT")
                git(git_root, "var", "GIT_COMMITTER_IDENT")
            except CheckpointError as error:
                raise CheckpointError("Git author/committer identity unavailable; configure identity and retry") from error
            commit_id = git(git_root, "commit-tree", tree_id, "-p", expected_head, input_bytes=message.encode("utf-8")).stdout.decode().strip()
            verify_commit_git_states(git_root, commit_id, declared_repo_paths, declared_paths, declared_git_states)
            verify_states(workspace_root, declared_states)
            if output(git_root, "rev-parse", "HEAD") != expected_head or output(git_root, "symbolic-ref", "-q", "HEAD") != expected_ref:
                raise CheckpointError("HEAD or branch changed before checkpoint update")
            if index_digest(index_entries(git_root), set(declared_repo_paths)) != prior_index_digest:
                raise CheckpointError("user index changed before checkpoint update")
            zero_oid = "0" * len(expected_head)
            index_info = bytearray()
            for repo_path, workspace_path in zip(declared_repo_paths, declared_paths):
                state = declared_git_states[workspace_path]
                if state["type"] == "missing":
                    index_info.extend(f"0 {zero_oid}\t".encode("ascii"))
                else:
                    index_info.extend(f"{state['mode']} {state['oid']}\t".encode("ascii"))
                index_info.extend(os.fsencode(repo_path))
                index_info.extend(b"\x00")
            if original_index is None:
                raise CheckpointError("repository index is missing")
            desired_descriptor, desired_index_name = tempfile.mkstemp(prefix=".checkpoint-real-index-", dir=workflow_root / "snapshots")
            desired_index = Path(desired_index_name)
            try:
                with os.fdopen(desired_descriptor, "wb") as desired_stream:
                    desired_stream.write(original_index)
                git(git_root, "update-index", "-z", "--index-info", input_bytes=bytes(index_info), index_file=desired_index)
                desired_entries = index_entries(git_root, desired_index)
                verify_index_git_states(desired_entries, declared_repo_paths, declared_paths, declared_git_states)
                if index_digest(desired_entries, set(declared_repo_paths)) != prior_index_digest:
                    raise CheckpointError("desired checkpoint index changes user entries")
                desired_content = desired_index.read_bytes()
            finally:
                desired_index.unlink(missing_ok=True)
                desired_index.with_name(f"{desired_index.name}.lock").unlink(missing_ok=True)
            lock_metadata = {
                "schema": "orchestrator-index-lock-v1",
                "pid": os.getpid(),
                "request_id": request_path.stem,
                "expected_head": expected_head,
                "index_sha256": hashlib.sha256(desired_content).hexdigest(),
            }
            lock_owned = False
            metadata_descriptor = os.open(lock_metadata_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(metadata_descriptor, "wb") as metadata_stream:
                    metadata_stream.write((json.dumps(lock_metadata, sort_keys=True) + "\n").encode("utf-8"))
                    metadata_stream.flush()
                    os.fsync(metadata_stream.fileno())
                lock_descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IMODE(git_path.stat().st_mode))
                lock_owned = True
            except BaseException:
                lock_metadata_path.unlink(missing_ok=True)
                raise
            try:
                if git_path.read_bytes() != original_index:
                    raise CheckpointError("repository index changed before lock")
                with os.fdopen(lock_descriptor, "wb", closefd=False) as lock_stream:
                    lock_stream.write(desired_content)
                    lock_stream.flush()
                    os.fsync(lock_stream.fileno())
                os.close(lock_descriptor)
                lock_descriptor = -1
                if output(git_root, "rev-parse", "HEAD") != expected_head or output(git_root, "symbolic-ref", "-q", "HEAD") != expected_ref:
                    raise CheckpointError("HEAD or branch changed while index locked")
                git(git_root, "update-ref", expected_ref, commit_id, expected_head)
                committed = True
                os.replace(lock_path, git_path)
                lock_owned = False
                lock_metadata_path.unlink(missing_ok=True)
            finally:
                if lock_descriptor >= 0:
                    try:
                        os.close(lock_descriptor)
                    except OSError:
                        pass
                if not committed and lock_owned:
                    lock_path.unlink(missing_ok=True)
                if not committed:
                    lock_metadata_path.unlink(missing_ok=True)
        except BaseException:
            raise
        finally:
            temporary_index.unlink(missing_ok=True)
            temporary_index.with_name(f"{temporary_index.name}.lock").unlink(missing_ok=True)
    commit_id = output(git_root, "rev-parse", "HEAD")
    if output(git_root, "rev-parse", f"{commit_id}^") != expected_head:
        raise CheckpointError("checkpoint parent mismatch")
    if output(git_root, "symbolic-ref", "-q", "HEAD") != expected_ref:
        raise CheckpointError("branch changed during checkpoint")
    committed_paths = nul_paths(git(git_root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", commit_id).stdout)
    if committed_paths != set(declared_repo_paths):
        raise CheckpointError(f"checkpoint path mismatch: {sorted(committed_paths)!r}")
    verify_commit_git_states(git_root, commit_id, declared_repo_paths, declared_paths, declared_git_states)
    commit_message = output(git_root, "show", "-s", "--format=%B", commit_id)
    expected_trailers = (f"Workflow-ID: {workflow_root.name}", f"Stage-ID: {stage}", f"Product-Snapshot-ID: {product_snapshot_id}", f"Review-Epoch-ID: {review_epoch_id}", f"Plan-Structure-ID: {plan_structure_id}")
    if any(trailer not in commit_message for trailer in expected_trailers):
        raise CheckpointError("checkpoint trailers mismatch")
    verify_states(workspace_root, declared_states)
    if already_committed and lock_path.exists():
        if not lock_metadata_path.exists():
            raise CheckpointError("repository index is locked by another process")
        recover_orchestrator_index_lock(git_path, expected_head, commit_id, request_path.stem)
        recovery_entries = index_entries(git_root, lock_path)
        verify_index_git_states(recovery_entries, declared_repo_paths, declared_paths, declared_git_states)
        if index_digest(recovery_entries, set(declared_repo_paths)) != prior_index_digest:
            raise CheckpointError("checkpoint index lock changes user entries")
        os.replace(lock_path, git_path)
        lock_metadata_path.unlink(missing_ok=True)
    after_index = index_entries(git_root)
    if index_digest(after_index, set(declared_repo_paths)) != prior_index_digest:
        raise CheckpointError("checkpoint changed user index entries")
    remaining_workflow_changes = changed_paths(git_root).intersection(declared_repo_paths)
    if remaining_workflow_changes:
        raise CheckpointError(f"checkpoint left workflow changes: {sorted(remaining_workflow_changes)!r}")
    committed_tree_id = output(git_root, "rev-parse", f"{commit_id}^{{tree}}")
    payload = checkpoint_payload(request, commit_id, committed_tree_id, expected_head, expected_ref, declared_paths)
    result_path = workflow_root / "snapshots" / f"checkpoint-{stage}-{commit_id}.json"
    if result_path.exists():
        if json.loads(result_path.read_text(encoding="utf-8")) != payload:
            raise CheckpointError("checkpoint result conflicts with commit")
    else:
        atomic_json(workspace_root, result_path, payload)
    request["state"] = "COMPLETED"
    request["result"] = str(result_path.relative_to(workflow_root))
    atomic_json(workspace_root, request_path, request)
    return payload


def main() -> int:
    try:
        if sys.argv[1:] == ["--index-digest"]:
            root = Path(output(Path.cwd().resolve(), "rev-parse", "--show-toplevel")).resolve()
            print(index_digest(index_entries(root), set()))
            return 0
        if len(sys.argv) != 1:
            raise CheckpointError("usage: checkpoint.py [--index-digest]")
        result = checkpoint(Path.cwd().resolve())
    except (CheckpointError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"checkpoint: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
