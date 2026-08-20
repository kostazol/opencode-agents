from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .action_builder import complete_action, first_unfinished, normalize_progress, pending_action
from .model import stage_index, validate_state
from .protocol import ProtocolError
from .traceability import validate_execution_graph


def reserve_next(
    value: Mapping[str, Any], analysis: Mapping[str, Any] | None = None, *,
    expected_state_revision: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cross_check = analysis if analysis is not None and value.get("stages") and not value.get("legacy_migrated") else None
    state = validate_state(value, cross_check)
    if expected_state_revision is not None and state["state_revision"] != expected_state_revision:
        raise ProtocolError("expected_state_revision", "state revision conflict", {
            "expected": expected_state_revision, "actual": state["state_revision"],
        })
    if state["pending"] is not None:
        return state, deepcopy(state["pending"])
    if state["status"] == "ready":
        return state, complete_action(state)

    next_state = deepcopy(state)
    normalize_progress(next_state)
    status = next_state["status"]
    if status == "ready":
        return next_state, complete_action(next_state)

    if status == "discovery":
        next_state["analysis_revision"] += 1
        next_state["analysis_status"] = "draft"
        action = pending_action(
            next_state, "DISCOVER", "orchestrator-discovery", "collect-and-structure-evidence",
            mode="INITIAL" if next_state["analysis_revision"] == 1 else "FOLLOW_UP",
            revision=next_state["analysis_revision"],
            inputs=[path for path in ("discovery.md", "questions.md", "feedback.md") if path != "questions.md" or next_state["question_revision"]],
            output="analysis.json",
        )
    elif status == "discovery_review":
        if analysis is None:
            raise ProtocolError("analysis", "discovery review requires analysis.json")
        validate_execution_graph(analysis)
        action = pending_action(
            next_state, "REVIEW_DISCOVERY", "orchestrator-stage-reviewer", "independent-discovery-quality-gate",
            mode="DISCOVERY", revision=next_state["analysis_revision"],
            inputs=["analysis.json", "discovery.md"], output="reviews/discovery.md",
        )
    elif status == "waiting_answers":
        action = pending_action(
            next_state, "ASK_QUESTIONS", "user", "material-user-decisions-required",
            revision=next_state["question_revision"], inputs=["questions.md"],
        )
    elif status == "waiting_map_approval":
        action = pending_action(
            next_state, "APPROVE_MAP", "user", "reviewed-stage-map-requires-user-approval",
            revision=next_state["analysis_revision"],
            inputs=["plan.md", "analysis.json", "reviews/discovery.md"],
        )
    elif status == "planning":
        if analysis is None:
            raise ProtocolError("analysis", "stage planning requires analysis.json")
        validate_execution_graph(analysis)
        current = first_unfinished(next_state, "status")
        if current is None:
            raise ProtocolError("stages", "planning has no unfinished stage")
        next_state["current_stage"] = current["id"]
        dependencies = [stage_index(next_state)[item]["details"] for item in current["depends_on"]]
        if current["status"] in {"proposed", "planning"}:
            if current["status"] == "proposed":
                current["revision"] += 1
                current["status"] = "planning"
            action = pending_action(
                next_state, "PLAN_STAGE", "orchestrator-stage-planner", "create-or-correct-current-stage-plan",
                mode="TECHNICAL", stage=current["id"], revision=current["revision"],
                inputs=["analysis.json", "discovery.md", "plan.md", *dependencies], output=current["details"],
            )
        else:
            action = pending_action(
                next_state, "REVIEW_STAGE", "orchestrator-stage-reviewer", "independent-current-stage-review",
                mode="TECHNICAL", stage=current["id"], revision=current["revision"],
                inputs=["analysis.json", "discovery.md", "plan.md", current["details"], *dependencies], output=current["review"],
            )
    elif status == "human_reviewing":
        current = first_unfinished(next_state, "human_status")
        if current is None:
            raise ProtocolError("stages", "human review has no unfinished stage")
        next_state["current_stage"] = current["id"]
        if current["human_status"] in {"pending", "planning"}:
            if current["human_status"] == "pending":
                current["human_revision"] += 1
                current["human_status"] = "planning"
            action = pending_action(
                next_state, "PLAN_HUMAN_REVIEW", "orchestrator-stage-planner", "create-user-readable-stage-plan",
                mode="HUMAN_REVIEW", stage=current["id"], revision=current["human_revision"],
                source_revision=current["revision"],
                inputs=["analysis.json", "plan.md", current["details"], current["review"]], output=current["human_review"],
            )
        else:
            action = pending_action(
                next_state, "REVIEW_HUMAN_REVIEW", "orchestrator-stage-reviewer", "independent-human-review-fidelity-gate",
                mode="HUMAN_REVIEW", stage=current["id"], revision=current["human_revision"],
                source_revision=current["revision"],
                inputs=["analysis.json", "plan.md", current["details"], current["review"], current["human_review"]],
                output=current["human_review_review"],
            )
    elif status == "waiting_plan_approval":
        action = pending_action(
            next_state, "APPROVE_PLAN", "user", "fully-reviewed-plan-requires-user-approval",
            inputs=["plan.md", *[item["human_review"] for item in next_state["stages"]]],
        )
    elif status == "waiting_reopen_approval":
        action = pending_action(
            next_state, "APPROVE_REOPEN", "user", "passed-stage-reopening-requires-user-approval",
            inputs=["plan.md", "analysis.json"],
        )
    elif status == "blocked":
        action = pending_action(
            next_state, "RESOLVE_BLOCKER", "user", "workflow-blocker-requires-resolution", inputs=["plan.md"],
        )
    else:
        raise ProtocolError("status", "no action for workflow status", status)
    return validate_state(next_state, analysis if analysis is not None and next_state["stages"] and not next_state["legacy_migrated"] else None), deepcopy(action)
