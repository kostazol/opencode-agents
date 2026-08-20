from __future__ import annotations

import re
from typing import Any, Mapping

from .protocol import ProtocolError, STATE_SCHEMA_VERSION, validate_analysis

REQUEST_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
WORKFLOW_STATUSES = {
    "discovery", "discovery_review", "waiting_answers", "waiting_map_approval",
    "planning", "human_reviewing", "waiting_plan_approval",
    "waiting_reopen_approval", "ready", "blocked",
}
ANALYSIS_STATUSES = {"missing", "draft", "review", "reviewed", "approved"}
STAGE_STATUSES = {"proposed", "planning", "review", "pass"}
HUMAN_STATUSES = {"pending", "planning", "review", "pass"}
ACTIONS = {
    "DISCOVER", "REVIEW_DISCOVERY", "ASK_QUESTIONS", "APPROVE_MAP",
    "PLAN_STAGE", "REVIEW_STAGE", "PLAN_HUMAN_REVIEW",
    "REVIEW_HUMAN_REVIEW", "APPROVE_PLAN", "APPROVE_REOPEN",
    "RESOLVE_BLOCKER",
}
STATE_FIELDS = {
    "schema_version", "request_id", "state_revision", "sequence", "status",
    "current_stage", "analysis_revision", "analysis_status", "question_revision",
    "feedback_revision", "stages", "pending", "applied", "blocker", "reopen",
    "legacy_migrated",
}
STAGE_FIELDS = {
    "id", "title", "slug", "depends_on", "status", "revision",
    "human_status", "human_revision", "details", "review", "human_review",
    "human_review_review",
}
PENDING_FIELDS = {
    "transition_id", "action", "actor", "mode", "stage", "revision",
    "source_revision", "inputs", "output", "reason", "issued_state_revision",
}


def state_error(field: str, message: str, value: Any = None) -> ProtocolError:
    return ProtocolError(field, message, value)


def require_integer(value: Any, field: str, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise state_error(field, f"must be an integer >= {minimum}", value)


def new_state(request_id: str) -> dict[str, Any]:
    if REQUEST_ID.fullmatch(request_id) is None:
        raise state_error("request_id", "must be lower kebab-case and at most 80 characters", request_id)
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "request_id": request_id,
        "state_revision": 0,
        "sequence": 0,
        "status": "discovery",
        "current_stage": None,
        "analysis_revision": 0,
        "analysis_status": "missing",
        "question_revision": 0,
        "feedback_revision": 0,
        "stages": [],
        "pending": None,
        "applied": {},
        "blocker": None,
        "reopen": None,
        "legacy_migrated": False,
    }


def stages_from_analysis(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in validate_analysis(analysis)["stages"]:
        number = int(item["id"][1:])
        slug = item["slug"]
        result.append({
            "id": item["id"], "title": item["title"], "slug": slug,
            "depends_on": list(item["depends_on"]), "status": "proposed",
            "revision": 0, "human_status": "pending", "human_revision": 0,
            "details": f"stages/{number:02d}-{slug}.md",
            "review": f"reviews/{number:02d}.md",
            "human_review": f"stages/{number:02d}-{slug}.human-review.md",
            "human_review_review": f"reviews/{number:02d}-human-review.md",
        })
    return result


def stage_index(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {stage["id"]: stage for stage in state["stages"]}
