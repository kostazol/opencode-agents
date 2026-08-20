from __future__ import annotations

from typing import Any, Mapping

from .model import stage_index
from .protocol import ProtocolError, affected_stage_closure


def _seeds(payload: Mapping[str, Any]) -> list[str]:
    values = payload.get("affected_stages")
    if not isinstance(values, list) or not values or any(not isinstance(item, str) for item in values):
        raise ProtocolError("event.payload.affected_stages", "must contain stage identifiers")
    if len(values) != len(set(values)):
        raise ProtocolError("event.payload.affected_stages", "must not contain duplicates")
    return values


def _reason(payload: Mapping[str, Any]) -> str:
    value = payload.get("reason") or payload.get("remarks")
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("event.payload.reason", "reopening requires a reason")
    return " ".join(value.split())


def affected_from_payload(analysis: Mapping[str, Any], payload: Mapping[str, Any]) -> tuple[list[str], list[str], str]:
    seeds = _seeds(payload)
    return seeds, affected_stage_closure(analysis, seeds), _reason(payload)


def propose_reopen(
    state: dict[str, Any], analysis: Mapping[str, Any], payload: Mapping[str, Any], requested_by: str,
) -> dict[str, Any]:
    seeds, affected, reason = affected_from_payload(analysis, payload)
    state["reopen"] = {
        "requested_by": requested_by,
        "reason": reason,
        "seeds": seeds,
        "affected": affected,
        "resume_status": state["status"],
        "resume_stage": state["current_stage"],
    }
    state["status"] = "waiting_reopen_approval"
    return {"status": "waiting_reopen_approval", "affected": affected, "reason": reason}


def apply_reopen(state: dict[str, Any], analysis: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    proposal = state["reopen"]
    if proposal is None:
        raise ProtocolError("reopen", "no reopening proposal exists")
    decision = payload.get("decision")
    if decision not in {"APPROVE", "REJECT"}:
        raise ProtocolError("event.payload.decision", "must be APPROVE or REJECT", decision)
    if decision == "REJECT":
        state["status"] = proposal["resume_status"]
        state["current_stage"] = proposal["resume_stage"]
        state["reopen"] = None
        return {"status": state["status"], "reopened": []}
    affected = affected_stage_closure(analysis, proposal["seeds"])
    if affected != proposal["affected"]:
        raise ProtocolError("reopen", "proposal is stale for the current dependency graph", {"reserved": proposal["affected"], "current": affected})
    stages = stage_index(state)
    for stage_id in affected:
        stage = stages[stage_id]
        stage["status"] = "proposed"
        stage["human_status"] = "pending"
    state["status"] = "planning"
    state["current_stage"] = affected[0]
    state["reopen"] = None
    state["convergence"] = {key: value for key, value in state["convergence"].items() if not any(stage in key for stage in affected)}
    return {"status": "planning", "reopened": affected, "current_stage": affected[0]}


def reopen_directly(state: dict[str, Any], analysis: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    seeds, affected, reason = affected_from_payload(analysis, payload)
    stages = stage_index(state)
    for stage_id in affected:
        stages[stage_id]["status"] = "proposed"
        stages[stage_id]["human_status"] = "pending"
    state["status"] = "planning"
    state["current_stage"] = affected[0]
    state["feedback_revision"] += 1
    state["convergence"] = {key: value for key, value in state["convergence"].items() if not any(stage in key for stage in affected)}
    return {"status": "planning", "reopened": affected, "reason": reason, "feedback_revision": state["feedback_revision"]}
