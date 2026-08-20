from __future__ import annotations

from typing import Any, Mapping

from .model import validate_state
from .traceability import validate_execution_graph


def _items(values: list[str]) -> str:
    return "none" if not values else f"[{', '.join(values)}]"


def render_plan(state_value: Mapping[str, Any], analysis_value: Mapping[str, Any] | None = None) -> str:
    cross_check = analysis_value if analysis_value is not None and state_value.get("stages") and not state_value.get("legacy_migrated") else None
    state = validate_state(state_value, cross_check)
    analysis = validate_execution_graph(analysis_value) if analysis_value is not None else None
    lines = [
        "---", "schema_version: 1", f"state_revision: {state['state_revision']}",
        f"status: {state['status']}", f"current_stage: {state['current_stage'] or 'none'}",
        f"analysis_revision: {state['analysis_revision']}", "---", "# План реализации", "",
        "> Индекс генерируется controller; смысловые детали находятся в discovery, stage и review artifacts.", "",
        "## Состояние", "", f"- Запрос: `{state['request_id']}`",
        f"- Workflow: `{state['status']}`",
        f"- Analysis: `{state['analysis_status']}` revision {state['analysis_revision']}",
        f"- Feedback revision: {state['feedback_revision']}",
    ]
    if state["pending"]:
        lines += [
            f"- Pending: `{state['pending']['transition_id']}` / `{state['pending']['action']}`",
            f"- Pending reason: {state['pending']['reason']}",
        ]
    if state["blocker"]:
        lines += ["", "## Blocker", "", f"- Reason: {state['blocker']['reason']}", f"- Detail: {state['blocker']['detail']}"]
    lines += ["", "## Stage map", ""]
    sources = {item["id"]: item for item in analysis["stages"]} if analysis else {}
    for stage in state["stages"]:
        source = sources.get(stage["id"], {})
        lines += [
            f"### {stage['id']} — {stage['title']}",
            f"- Status: {stage['status'].upper()}", f"- Revision: {stage['revision']}",
            f"- Depends on: {_items(stage['depends_on'])}",
            f"- Affected area: {source.get('affected_area', 'unknown')}",
            f"- Primary risks: {_items(source.get('risks', []))}",
            f"- Consumes: {_items(source.get('contracts_consumed', []))}",
            f"- Produces: {_items(source.get('contracts_produced', []))}",
            f"- Details: {stage['details']}", f"- Review: {stage['review']}",
            f"- Human review: {stage['human_review']}",
            f"- Human review revision: {stage['human_revision']}",
            f"- Human review status: {stage['human_status'].upper()}",
            f"- Human review review: {stage['human_review_review']}", "",
        ]
    if analysis:
        lines += ["## Traceability", ""]
        for item in [*analysis["requirements"], *analysis["nfrs"]]:
            category = f" ({item['category']})" if "category" in item else ""
            lines.append(
                f"- `{item['id']}`{category} → `{item['stage']}` → {_items(item['scenarios'])} → {_items(item['acceptance'])}: {item['text']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
