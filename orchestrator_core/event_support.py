from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .model import stage_index
from .protocol import ProtocolError

AGENT_ACTIONS = {
    "DISCOVER", "REVIEW_DISCOVERY", "PLAN_STAGE", "REVIEW_STAGE",
    "PLAN_HUMAN_REVIEW", "REVIEW_HUMAN_REVIEW",
}
EVENT_BY_ACTION = {
    "DISCOVER": "discovery_result",
    "REVIEW_DISCOVERY": "discovery_review_result",
    "ASK_QUESTIONS": "answers",
    "APPROVE_MAP": "map_decision",
    "PLAN_STAGE": "stage_plan_result",
    "REVIEW_STAGE": "stage_review_result",
    "PLAN_HUMAN_REVIEW": "human_plan_result",
    "REVIEW_HUMAN_REVIEW": "human_review_result",
    "APPROVE_PLAN": "plan_decision",
    "APPROVE_REOPEN": "reopen_decision",
    "RESOLVE_BLOCKER": "blocker_resolution",
}
FAILURE_REASONS = {"timeout", "cancelled", "permission_denied", "malformed_result", "tool_error"}


def digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def choice(payload: Mapping[str, Any], field: str, values: set[str]) -> str:
    value = payload.get(field)
    if value not in values:
        raise ProtocolError(f"event.payload.{field}", "unsupported value", value)
    return value


def revision(payload: Mapping[str, Any], expected: int) -> None:
    value = payload.get("revision")
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise ProtocolError("event.payload.revision", f"must equal reserved revision {expected}", value)


def stage_for(state: dict[str, Any], pending: Mapping[str, Any]) -> dict[str, Any]:
    stage_id = pending["stage"]
    if stage_id is None or stage_id not in stage_index(state):
        raise ProtocolError("pending.stage", "action requires a known stage", stage_id)
    return stage_index(state)[stage_id]


def block(
    state: dict[str, Any], pending: Mapping[str, Any], reason: str,
    detail: str, retryable: bool = True,
) -> dict[str, Any]:
    resume_status = state["status"]
    state["status"] = "blocked"
    state["blocker"] = {
        "reason": reason, "detail": detail, "resume_status": resume_status,
        "retryable": retryable, "source_transition": pending["transition_id"],
    }
    return {"status": "blocked", "reason": reason, "retryable": retryable}
