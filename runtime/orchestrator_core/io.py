from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Iterator, Mapping

from .protocol import ProtocolError, load_json


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "wb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def exclusive_lock(path: Path, *, timeout: float = 5.0, stale_after: float = 300.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    metadata = json_bytes({"pid": os.getpid(), "created_at": datetime.now(timezone.utc).isoformat()})
    while True:
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as target:
                target.write(metadata)
                target.flush()
                os.fsync(target.fileno())
            break
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > stale_after:
                path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise ProtocolError("workflow_lock", "request is already being advanced", str(path))
            time.sleep(0.025)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ProtocolError(f"journal[{number}]", "invalid JSON", line) from error
        if not isinstance(value, dict) or "entry_id" not in value:
            raise ProtocolError(f"journal[{number}]", "invalid record", value)
        records.append(value)
    return records


def append_jsonl_once(path: Path, record: Mapping[str, Any]) -> None:
    records = read_jsonl(path)
    if any(item["entry_id"] == record["entry_id"] for item in records):
        return
    records.append(dict(record))
    content = b"".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        for item in records
    )
    atomic_write(path, content)


def recover_transaction(transaction_path: Path, state_path: Path, plan_path: Path, journal_path: Path) -> bool:
    if not transaction_path.exists():
        return False
    transaction = load_json(transaction_path)
    if set(transaction) != {"schema_version", "state", "plan", "journal"} or transaction["schema_version"] != 1:
        raise ProtocolError("transaction", "unsupported recovery transaction")
    atomic_write(state_path, json_bytes(transaction["state"]))
    atomic_write(plan_path, transaction["plan"].encode(), 0o644)
    append_jsonl_once(journal_path, transaction["journal"])
    transaction_path.unlink(missing_ok=True)
    return True
