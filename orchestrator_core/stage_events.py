from __future__ import annotations

from typing import Any, Mapping

from .convergence import clear_review, record_revise
from .event_support import block, choice, revision, stage_for
from .protocol import ProtocolError
from .reopening import propose_reopen


def _revise(
    state: dict[str, Any], pending: Mapping[str, Any], payload: Mapping[str, Any],
    key: str, status_field: str, pending_status: str, workflow_status: str,
) -> dict[str, Any]:
    stage = stage_for(state, pending)
    stalled, summary = record_revise(state, key, pending["revision"], payload)
    stage[status_field] = pending_status
    state["status"] = workflow_status
    if stalled:
        return block(state, pending, "no_semantic_progress", f"Repeated unchanged findings: {summary}", True)
    return {"status": workflow_status, "stage": stage["id"], "next_revision": pending["revision"] + 1}


def apply_stage_action(
    state: dict[str, Any], pending: Mapping[str, Any], payload: Mapping[str, Any],
    analysis: Mapping[str, Any] | None,
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
        status = choice(payload, "status", {"PASS", "REVISE", "REOPEN", "BLOCKED"})
        key = f"TECHNICAL:{stage['id']}"
        if status == "PASS":
            clear_review(state, key)
            stage["status"] = "pass"
            return {"status": "pass", "stage": stage["id"], "revision": stage["revision"]}
        if status == "REVISE":
            return _revise(state, pending, payload, key, "status", "proposed", "planning")
        if status == "REOPEN":
            if analysis is None:
                raise ProtocolError("analysis", "reopening requires analysis.json")
            return propose_reopen(state, analysis, payload, "reviewer")
        return block(state, pending, "stage_review_blocked", str(payload.get("detail", "Stage review blocked")), bool(payload.get("retryable", True)))

    if action == "PLAN_HUMAN_REVIEW":
        status = choice(payload, "status", {"REVIEW", "BLOCKED"})
        if status == "REVIEW":
            stage["human_status"] = "review"
            return {"status": "review", "stage": stage["id"], "revision": stage["human_revision"]}
        return block(state, pending, "human_plan_blocked", str(payload.get("detail", "Human-review planning blocked")), bool(payload.get("retryable", True)))

    if action == "REVIEW_HUMAN_REVIEW":
        status = choice(payload, "status", {"PASS", "REVISE", "REOPEN", "BLOCKED"})
        key = f"HUMAN:{stage['id']}"
        if status == "PASS":
            clear_review(state, key)
            stage["human_status"] = "pass"
            return {"status": "pass", "stage": stage["id"], "revision": stage["human_revision"]}
        if status == "REVISE":
            return _revise(state, pending, payload, key, "human_status", "pending", "human_reviewing")
        if status == "REOPEN":
            if analysis is None:
                raise ProtocolError("analysis", "reopening requires analysis.json")
            return propose_reopen(state, analysis, payload, "reviewer")
        return block(state, pending, "human_review_blocked", str(payload.get("detail", "Human review blocked")), bool(payload.get("retryable", True)))

    raise ProtocolError("pending.action", "not a stage action", action)
