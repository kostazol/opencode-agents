#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrator_core.protocol import ProtocolError  # noqa: E402
from orchestrator_core.store import WorkflowStore  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("operation", choices=("next", "apply", "validate"))
    result.add_argument("--directory", required=True)
    result.add_argument("--request", required=True)
    return result


def body() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ProtocolError("input", "must be a JSON object")
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        payload = body()
        store = WorkflowStore(Path(args.directory), args.request)
        if args.operation == "next":
            state, action = store.reserve(expected_state_revision=payload.get("expected_state_revision"))
            result = {"ok": True, "state_revision": state["state_revision"], "status": state["status"], "action": action}
        elif args.operation == "apply":
            event = {
                "transition_id": payload.get("transition_id"),
                "type": payload.get("event_type"),
                "payload": payload.get("payload"),
            }
            state, applied = store.apply(event, expected_state_revision=payload.get("expected_state_revision"))
            result = {"ok": True, "state_revision": state["state_revision"], "status": state["status"], "result": applied}
        else:
            result = {"ok": True, "validation": store.validate()}
    except ProtocolError as error:
        result = {"ok": False, "error": {"type": "protocol", "field": error.field, "message": str(error), "value": error.value}}
    except Exception as error:
        result = {"ok": False, "error": {"type": "runtime", "message": str(error)}}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
