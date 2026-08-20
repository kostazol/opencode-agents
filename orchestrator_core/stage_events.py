from __future__ import annotations

from typing import Any, Mapping

from .event_support import block, choice, revision, stage_for
from .protocol import ProtocolError


def apply_stage_action(
    state: dict[str, Any], pending: Mapping[str, Any], payload: Mapping[str, Any],
) -> dict[str, Any]:
    action = pending["action"]
    stage = stage_for(state, pending)
    revision(payload, pending["revision"])

    if action == "PLAN_STAGE":
        status = choice(payload, "status", {"REVIEW", "BLOCKED"})
        if status == "REVIEW":
            stage["status"] = "review"
            return {"status": "review", "stage": stage["id"], "revision": stage["revision"]}
        return block(state, pending, "stage_plan_blocked", str(payload.get("detail", "Stage planning blocked")), bool(payload.get("retryable", True)))

    if action == "REVIEW_STAGE":
        status = choice(payload, "status", {"PASS", "REVISE", "BLOCKED"})
        if status == "PASS":
            stage["status"] = "pass"
            return {"status": "pass", "stage": stage["id"], "revision": stage["revision"]}
        if status == "REVISE":
            stage["status"] = "proposed"
            return {"status": "planning", "stage": stage["id"], "next_revision": stage["revision"] + 1}
        return block(state, pending, "stage_review_blocked", str(payload.get("detail", "Stage review blocked")), bool(payload.get("retryable", True)))

    if action == "PLAN_HUMAN_REVIEW":
        status = choice(payload, "status", {"REVIEW", "BLOCKED"})
        if status == "REVIEW":
            stage["human_status"] = "review"
            return {"status": "review", "stage": stage["id"], "revision": stage["human_revision"]}
        return block(state, pending, "human_plan_blocked", str(payload.get("detail", "Human-review planning blocked")), bool(payload.get("retryable", True)))

    if action == "REVIEW_HUMAN_REVIEW":
        status = choice(payload, "status", {"PASS", "REVISE", "BLOCKED"})
        if status == "PASS":
            stage["human_status"] = "pass"
            return {"status": "pass", "stage": stage["id"], "revision": stage["human_revision"]}
        if status == "REVISE":
            stage["human_status"] = "pending"
            return {"status": "human_reviewing", "stage": stage["id"], "next_revision": stage["human_revision"] + 1}
        return block(state, pending, "human_review_blocked", str(payload.get("detail", "Human review blocked")), bool(payload.get("retryable", True)))

    raise ProtocolError("pending.action", "not a stage action", action)
