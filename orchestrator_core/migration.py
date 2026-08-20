from __future__ import annotations

from pathlib import Path
from typing import Any

from .legacy import parse_legacy_plan
from .model import new_state, validate_state


def legacy_to_state(path: Path, request_id: str) -> dict[str, Any]:
    parsed = parse_legacy_plan(path)
    state = new_state(request_id)
    state["legacy_migrated"] = True
    state["analysis_status"] = "draft"
    status_map = {"PROPOSED": "proposed", "PLANNING": "planning", "REVIEW": "review", "PASS": "pass"}
    human_map = {"PENDING": "pending", "REVIEW": "review", "PASS": "pass"}
    for item in parsed["stages"]:
        slug = Path(item["details"]).stem.split("-", 1)[1]
        state["stages"].append({
            "id": item["stage_id"], "title": item["title"], "slug": slug,
            "depends_on": list(item["depends_on"]),
            "status": status_map.get(item["status"], "proposed"),
            "revision": item["revision"],
            "human_status": human_map.get(item["human_review_status"], "pending"),
            "human_revision": item["human_review_revision"],
            "details": item["details"], "review": item["review"],
            "human_review": item["human_review"],
            "human_review_review": item["human_review_review"],
        })
    return validate_state(state)
