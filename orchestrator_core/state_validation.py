from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .protocol import STATE_SCHEMA_VERSION, canonical_relative_path, validate_analysis
from .state_types import (
    ACTIONS, ANALYSIS_STATUSES, HUMAN_STATUSES, PENDING_FIELDS, REOPEN_FIELDS, REQUEST_ID,
    STAGE_FIELDS, STAGE_STATUSES, STATE_FIELDS, WORKFLOW_STATUSES,
    require_integer, state_error,
)


def validate_state(value: Mapping[str, Any], analysis: Mapping[str, Any] | None = None) -> dict[str, Any]:
    state = deepcopy(dict(value))
    if state.get("schema_version") == 1 and "convergence" not in state:
        state["schema_version"] = STATE_SCHEMA_VERSION
        state["convergence"] = {}
    if set(state) != STATE_FIELDS:
        raise state_error("state", "field mismatch", {
            "missing": sorted(STATE_FIELDS - set(state)),
            "unknown": sorted(set(state) - STATE_FIELDS),
        })
    if state["schema_version"] != STATE_SCHEMA_VERSION:
        raise state_error("schema_version", f"must be {STATE_SCHEMA_VERSION}", state["schema_version"])
    if REQUEST_ID.fullmatch(str(state["request_id"])) is None:
        raise state_error("request_id", "invalid request identifier", state["request_id"])
    for field in ("state_revision", "sequence", "analysis_revision", "question_revision", "feedback_revision"):
        require_integer(state[field], field)
    if state["status"] not in WORKFLOW_STATUSES:
        raise state_error("status", "unsupported workflow status", state["status"])
    if state["analysis_status"] not in ANALYSIS_STATUSES:
        raise state_error("analysis_status", "unsupported analysis status", state["analysis_status"])
    if not isinstance(state["stages"], list):
        raise state_error("stages", "must be an array")

    seen: set[str] = set()
    for number, stage in enumerate(state["stages"], start=1):
        prefix = f"stages[{number - 1}]"
        if not isinstance(stage, dict) or set(stage) != STAGE_FIELDS:
            raise state_error(prefix, "field mismatch")
        expected_id = f"S{number:02d}"
        if stage["id"] != expected_id:
            raise state_error(f"{prefix}.id", "stages must be contiguous and ordered", stage["id"])
        if not isinstance(stage["depends_on"], list) or any(item not in seen for item in stage["depends_on"]):
            raise state_error(f"{prefix}.depends_on", "must reference earlier stages", stage["depends_on"])
        seen.add(stage["id"])
        if stage["status"] not in STAGE_STATUSES or stage["human_status"] not in HUMAN_STATUSES:
            raise state_error(prefix, "unsupported stage status")
        require_integer(stage["revision"], f"{prefix}.revision")
        require_integer(stage["human_revision"], f"{prefix}.human_revision")
        for field, path_prefix in (
            ("details", "stages/"), ("review", "reviews/"),
            ("human_review", "stages/"), ("human_review_review", "reviews/"),
        ):
            canonical_relative_path(stage[field], f"{prefix}.{field}", path_prefix)
        if stage["status"] == "pass" and stage["revision"] == 0:
            raise state_error(f"{prefix}.revision", "passed stage requires a revision")
        if stage["human_status"] == "pass" and stage["human_revision"] == 0:
            raise state_error(f"{prefix}.human_revision", "passed human review requires a revision")

    if state["current_stage"] is not None and state["current_stage"] not in seen:
        raise state_error("current_stage", "unknown stage", state["current_stage"])
    if state["status"] in {"planning", "human_reviewing"} and state["stages"] and state["current_stage"] is None:
        raise state_error("current_stage", "active workflow requires a stage")

    pending = state["pending"]
    if pending is not None:
        _validate_pending(pending, state, seen)
    _validate_applied_and_blocker(state)

    _validate_reopen_and_convergence(state, seen)
    if not isinstance(state["legacy_migrated"], bool):
        raise state_error("legacy_migrated", "must be boolean")

    if analysis is not None and state["stages"]:
        expected = [
            (item["id"], item["title"], item["slug"], item["depends_on"])
            for item in validate_analysis(analysis)["stages"]
        ]
        actual = [(item["id"], item["title"], item["slug"], item["depends_on"]) for item in state["stages"]]
        if actual != expected:
            raise state_error("stages", "state stage map does not match analysis")
    return state


def _validate_pending(pending: Any, state: Mapping[str, Any], seen: set[str]) -> None:
    if not isinstance(pending, dict) or set(pending) != PENDING_FIELDS:
        raise state_error("pending", "field mismatch")
    if pending["action"] not in ACTIONS or not isinstance(pending["transition_id"], str):
        raise state_error("pending", "invalid action or transition identifier")
    if pending["stage"] is not None and pending["stage"] not in seen:
        raise state_error("pending.stage", "unknown stage", pending["stage"])
    if pending["revision"] is not None:
        require_integer(pending["revision"], "pending.revision", 1)
    if not isinstance(pending["inputs"], list):
        raise state_error("pending.inputs", "must be an array")
    for index, path in enumerate(pending["inputs"]):
        canonical_relative_path(path, f"pending.inputs[{index}]")
    if pending["output"] is not None:
        canonical_relative_path(pending["output"], "pending.output")
    if pending["issued_state_revision"] != state["state_revision"]:
        raise state_error("pending.issued_state_revision", "must equal current state revision")


def _validate_applied_and_blocker(state: Mapping[str, Any]) -> None:
    if not isinstance(state["applied"], dict):
        raise state_error("applied", "must be an object")
    for transition_id, record in state["applied"].items():
        if not isinstance(transition_id, str) or not isinstance(record, dict) or set(record) != {"event_digest", "result"}:
            raise state_error("applied", "invalid idempotency record", transition_id)
    blocker = state["blocker"]
    if (state["status"] == "blocked") != (blocker is not None):
        raise state_error("blocker", "must exist exactly when status is blocked")
    if blocker is not None:
        expected = {"reason", "detail", "resume_status", "retryable", "source_transition"}
        valid_resume = WORKFLOW_STATUSES - {"blocked", "ready"}
        if not isinstance(blocker, dict) or set(blocker) != expected or blocker["resume_status"] not in valid_resume:
            raise state_error("blocker", "invalid blocker")


def _validate_reopen_and_convergence(state: Mapping[str, Any], seen: set[str]) -> None:
    reopen = state["reopen"]
    if (state["status"] == "waiting_reopen_approval") != (reopen is not None):
        raise state_error("reopen", "must exist exactly while reopening waits for approval")
    if reopen is not None:
        if not isinstance(reopen, dict) or set(reopen) != REOPEN_FIELDS:
            raise state_error("reopen", "invalid reopening proposal")
        if reopen["requested_by"] not in {"reviewer", "user"}:
            raise state_error("reopen.requested_by", "unsupported requester")
        if not isinstance(reopen["reason"], str) or not reopen["reason"].strip():
            raise state_error("reopen.reason", "must be non-empty")
        for field in ("seeds", "affected"):
            values = reopen[field]
            if not isinstance(values, list) or not values or len(values) != len(set(values)) or any(item not in seen for item in values):
                raise state_error(f"reopen.{field}", "must contain unique known stages", values)
        if not set(reopen["seeds"]).issubset(reopen["affected"]):
            raise state_error("reopen", "affected stages must include all seeds")
        if reopen["resume_status"] not in WORKFLOW_STATUSES - {"blocked", "ready", "waiting_reopen_approval"}:
            raise state_error("reopen.resume_status", "unsupported resume status")
        if reopen["resume_stage"] is not None and reopen["resume_stage"] not in seen:
            raise state_error("reopen.resume_stage", "unknown stage")
    convergence = state["convergence"]
    if not isinstance(convergence, dict):
        raise state_error("convergence", "must be an object")
    for key, record in convergence.items():
        if not isinstance(key, str) or not key or not isinstance(record, dict) or set(record) != {"fingerprint", "evidence_digest", "repeats", "last_revision"}:
            raise state_error("convergence", "invalid review record", key)
        for field in ("fingerprint", "evidence_digest"):
            value = record[field]
            if not isinstance(value, str) or len(value) != 64:
                raise state_error(f"convergence.{key}.{field}", "must be a SHA-256 digest")
        require_integer(record["repeats"], f"convergence.{key}.repeats", 1)
        require_integer(record["last_revision"], f"convergence.{key}.last_revision", 1)
