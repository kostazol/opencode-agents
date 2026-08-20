from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .action_builder import normalize_progress
from .event_support import AGENT_ACTIONS, EVENT_BY_ACTION, FAILURE_REASONS, block, choice, digest
from .model import validate_state
from .non_stage_events import apply_non_stage
from .protocol import ProtocolError
from .stage_events import apply_stage_action

STAGE_ACTIONS = {"PLAN_STAGE", "REVIEW_STAGE", "PLAN_HUMAN_REVIEW", "REVIEW_HUMAN_REVIEW"}


def apply_event(
    value: Mapping[str, Any], event: Mapping[str, Any],
    analysis: Mapping[str, Any] | None = None, *,
    expected_state_revision: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cross_check = analysis if analysis is not None and value.get("stages") and not value.get("legacy_migrated") else None
    state = validate_state(value, cross_check)
    if not isinstance(event, Mapping) or set(event) != {"transition_id", "type", "payload"}:
        raise ProtocolError("event", "must contain transition_id, type and payload")
    transition_id = event["transition_id"]
    event_digest = digest(event)
    if transition_id in state["applied"]:
        record = state["applied"][transition_id]
        if record["event_digest"] != event_digest:
            raise ProtocolError("event", "transition was already applied with different payload", transition_id)
        return state, deepcopy(record["result"])
    if expected_state_revision is not None and state["state_revision"] != expected_state_revision:
        raise ProtocolError("expected_state_revision", "state revision conflict", {
            "expected": expected_state_revision, "actual": state["state_revision"],
        })
    pending = state["pending"]
    if pending is None or pending["transition_id"] != transition_id:
        raise ProtocolError("event.transition_id", "does not match pending transition", transition_id)
    if not isinstance(event["payload"], Mapping):
        raise ProtocolError("event.payload", "must be an object")

    payload = dict(event["payload"])
    next_state = deepcopy(state)
    if event["type"] == "task_failure":
        result = _apply_failure(next_state, pending, payload)
    else:
        expected = EVENT_BY_ACTION[pending["action"]]
        if event["type"] != expected:
            raise ProtocolError("event.type", f"expected {expected}", event["type"])
        if pending["action"] in STAGE_ACTIONS:
            result = apply_stage_action(next_state, pending, payload)
        else:
            result = apply_non_stage(next_state, pending, payload, analysis)

    next_state["pending"] = None
    next_state["state_revision"] += 1
    next_state["applied"][transition_id] = {"event_digest": event_digest, "result": deepcopy(result)}
    normalize_progress(next_state)
    cross_check = analysis if analysis is not None and next_state["stages"] and not next_state["legacy_migrated"] else None
    return validate_state(next_state, cross_check), deepcopy(result)


def _apply_failure(
    state: dict[str, Any], pending: Mapping[str, Any], payload: Mapping[str, Any],
) -> dict[str, Any]:
    if pending["action"] not in AGENT_ACTIONS:
        raise ProtocolError("event.type", "task_failure is valid only for agent actions")
    reason = choice(payload, "reason", FAILURE_REASONS)
    detail = payload.get("detail")
    retryable = payload.get("retryable", True)
    if not isinstance(detail, str) or not detail.strip() or not isinstance(retryable, bool):
        raise ProtocolError("event.payload", "task failure requires detail and boolean retryable")
    return block(state, pending, reason, detail.strip(), retryable)
