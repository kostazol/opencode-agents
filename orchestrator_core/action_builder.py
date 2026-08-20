from __future__ import annotations

import hashlib
from typing import Any, Mapping


def transition_id(state: Mapping[str, Any], action: str, stage: str | None, revision: int | None) -> str:
    sequence = state["sequence"]
    material = f"{state['request_id']}|{sequence}|{action}|{stage or '-'}|{revision or 0}"
    return f"T{sequence:06d}-{hashlib.sha256(material.encode()).hexdigest()[:12]}"


def pending_action(
    state: dict[str, Any], action: str, actor: str, reason: str, *,
    mode: str | None = None, stage: str | None = None,
    revision: int | None = None, source_revision: int | None = None,
    inputs: list[str] | None = None, output: str | None = None,
) -> dict[str, Any]:
    state["sequence"] += 1
    state["state_revision"] += 1
    value = {
        "transition_id": transition_id(state, action, stage, revision),
        "action": action, "actor": actor, "mode": mode, "stage": stage,
        "revision": revision, "source_revision": source_revision,
        "inputs": inputs or [], "output": output, "reason": reason,
        "issued_state_revision": state["state_revision"],
    }
    state["pending"] = value
    return value


def normalize_progress(state: dict[str, Any]) -> None:
    if state["status"] == "planning" and state["stages"] and all(item["status"] == "pass" for item in state["stages"]):
        state["status"] = "human_reviewing"
        state["current_stage"] = next((item["id"] for item in state["stages"] if item["human_status"] != "pass"), None)
    if state["status"] == "human_reviewing" and state["stages"] and all(item["human_status"] == "pass" for item in state["stages"]):
        state["status"] = "waiting_plan_approval"
        state["current_stage"] = None


def first_unfinished(state: Mapping[str, Any], field: str) -> dict[str, Any] | None:
    return next((item for item in state["stages"] if item[field] != "pass"), None)


def complete_action(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "transition_id": None, "action": "COMPLETE", "actor": "none",
        "mode": None, "stage": None, "revision": None,
        "source_revision": None, "inputs": ["plan.md"], "output": None,
        "reason": "workflow-ready", "issued_state_revision": state["state_revision"],
    }
