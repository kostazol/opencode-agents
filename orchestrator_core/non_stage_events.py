from __future__ import annotations

from typing import Any, Mapping

from .convergence import clear_review, record_revise
from .event_support import block, choice, revision
from .model import stage_index, stages_from_analysis
from .protocol import ProtocolError
from .reopening import apply_reopen, reopen_directly
from .traceability import validate_execution_graph


def remarks(payload: Mapping[str, Any]) -> str:
    value = payload.get("remarks")
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("event.payload.remarks", "feedback requires remarks")
    return " ".join(value.split())


def merge_legacy(state: dict[str, Any], stages: list[dict[str, Any]]) -> None:
    if not state["legacy_migrated"]:
        return
    previous = stage_index(state)
    for candidate in stages:
        old = previous.get(candidate["id"])
        if old and (old["title"], old["slug"], old["depends_on"]) == (candidate["title"], candidate["slug"], candidate["depends_on"]):
            for field in ("status", "revision", "human_status", "human_revision"):
                candidate[field] = old[field]
    state["legacy_migrated"] = False


def apply_non_stage(
    state: dict[str, Any], pending: Mapping[str, Any], payload: Mapping[str, Any],
    analysis: Mapping[str, Any] | None,
) -> dict[str, Any]:
    action = pending["action"]
    if action == "DISCOVER":
        revision(payload, pending["revision"])
        status = choice(payload, "status", {"QUESTIONS", "READY_FOR_REVIEW", "BLOCKED"})
        if status == "QUESTIONS":
            state["question_revision"] += 1
            state["status"] = "waiting_answers"
            return {"status": "waiting_answers", "question_revision": state["question_revision"]}
        if status == "READY_FOR_REVIEW":
            if analysis is None:
                raise ProtocolError("analysis", "READY_FOR_REVIEW requires analysis.json")
            validate_execution_graph(analysis)
            state["analysis_status"] = "review"
            state["status"] = "discovery_review"
            return {"status": "discovery_review", "analysis_revision": state["analysis_revision"]}
        return block(state, pending, "discovery_blocked", str(payload.get("detail", "Discovery blocked")), bool(payload.get("retryable", True)))

    if action == "REVIEW_DISCOVERY":
        revision(payload, pending["revision"])
        status = choice(payload, "status", {"PASS", "REVISE", "BLOCKED"})
        if status == "PASS":
            clear_review(state, "DISCOVERY")
            state["analysis_status"] = "reviewed"
            state["status"] = "waiting_map_approval"
            return {"status": "waiting_map_approval"}
        if status == "REVISE":
            stalled, summary = record_revise(state, "DISCOVERY", pending["revision"], payload)
            state["analysis_status"] = "draft"
            state["status"] = "discovery"
            if stalled:
                return block(state, pending, "no_semantic_progress", f"Repeated unchanged findings: {summary}", True)
            return {"status": "discovery", "reason": "discovery-review-revise"}
        return block(state, pending, "discovery_review_blocked", str(payload.get("detail", "Discovery review blocked")), bool(payload.get("retryable", True)))

    if action == "ASK_QUESTIONS":
        answers = payload.get("answers")
        if not isinstance(answers, list) or not answers or any(not isinstance(item, str) or not item.strip() for item in answers):
            raise ProtocolError("event.payload.answers", "must contain non-empty answers")
        state["status"] = "discovery"
        return {"status": "discovery", "answers": len(answers)}

    if action == "APPROVE_MAP":
        decision = choice(payload, "decision", {"APPROVE", "FEEDBACK"})
        if decision == "FEEDBACK":
            remarks(payload)
            state["feedback_revision"] += 1
            state["analysis_status"] = "draft"
            state["status"] = "discovery"
            state["convergence"] = {}
            return {"status": "discovery", "feedback_revision": state["feedback_revision"]}
        if analysis is None:
            raise ProtocolError("analysis", "map approval requires analysis.json")
        stages = stages_from_analysis(validate_execution_graph(analysis))
        merge_legacy(state, stages)
        state["stages"] = stages
        state["analysis_status"] = "approved"
        state["status"] = "planning"
        state["current_stage"] = stages[0]["id"]
        return {"status": "planning", "current_stage": state["current_stage"]}

    if action == "APPROVE_PLAN":
        decision = choice(payload, "decision", {"APPROVE", "FEEDBACK"})
        if decision == "APPROVE":
            state["status"] = "ready"
            state["current_stage"] = None
            return {"status": "ready"}
        remarks(payload)
        scope_payload = dict(payload)
        scope_payload.setdefault("scope", "DISCOVERY")
        scope = choice(scope_payload, "scope", {"STAGES", "DISCOVERY"})
        if scope == "STAGES":
            if analysis is None:
                raise ProtocolError("analysis", "stage feedback requires analysis.json")
            return reopen_directly(state, analysis, payload)
        state["feedback_revision"] += 1
        state["analysis_status"] = "draft"
        state["status"] = "discovery"
        state["current_stage"] = None
        state["convergence"] = {}
        for stage in state["stages"]:
            stage["status"] = "proposed"
            stage["human_status"] = "pending"
        return {"status": "discovery", "feedback_revision": state["feedback_revision"]}

    if action == "RESOLVE_BLOCKER":
        decision = choice(payload, "decision", {"RETRY", "ABORT"})
        blocker_value = state["blocker"]
        if blocker_value is None:
            raise ProtocolError("blocker", "no blocker to resolve")
        if decision == "RETRY":
            if not blocker_value["retryable"]:
                raise ProtocolError("event.payload.decision", "blocker is not retryable")
            if blocker_value["reason"] == "no_semantic_progress":
                remarks(payload)
                state["feedback_revision"] += 1
                state["convergence"] = {}
            state["status"] = blocker_value["resume_status"]
            state["blocker"] = None
            return {"status": state["status"], "retried": True}
        blocker_value["retryable"] = False
        return {"status": "blocked", "aborted": True}

    if action == "APPROVE_REOPEN":
        if analysis is None:
            raise ProtocolError("analysis", "reopening requires analysis.json")
        return apply_reopen(state, analysis, payload)
    raise ProtocolError("pending.action", "unsupported action", action)
