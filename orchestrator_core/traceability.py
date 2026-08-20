from __future__ import annotations

from typing import Any, Mapping

from .protocol import ProtocolError, validate_analysis


def validate_execution_graph(value: Mapping[str, Any]) -> dict[str, Any]:
    """Add implementation-order checks that are intentionally separate from JSON shape validation."""

    analysis = validate_analysis(value)
    stages = {item["id"]: item for item in analysis["stages"]}
    acceptance = {item["id"]: item for item in analysis["acceptance"]}
    scenarios = {item["id"]: item for item in analysis["scenarios"]}

    for decision in analysis["decisions"]:
        if set(decision) != {"id", "text"} or not isinstance(decision["text"], str) or not decision["text"].strip():
            raise ProtocolError(f"decisions[{decision.get('id', '?')}]", "must contain exactly id and non-empty text")

    for collection in (analysis["requirements"], analysis["nfrs"]):
        for item in collection:
            stage_id = item["stage"]
            if any(acceptance[value]["stage"] != stage_id for value in item["acceptance"]):
                raise ProtocolError(f"{item['id']}.acceptance", "acceptance must belong to the owning stage")
            if any(scenarios[value]["stage"] != stage_id for value in item["scenarios"]):
                raise ProtocolError(f"{item['id']}.scenarios", "scenarios must belong to the owning stage")

    for contract in analysis["contracts"]:
        producer = contract["producer"]
        if producer is None:
            continue
        for consumer in contract["consumers"]:
            dependencies = set(stages[consumer]["depends_on"])
            frontier = list(dependencies)
            while frontier:
                current = frontier.pop()
                for parent in stages[current]["depends_on"]:
                    if parent not in dependencies:
                        dependencies.add(parent)
                        frontier.append(parent)
            if producer not in dependencies:
                raise ProtocolError(
                    f"contracts[{contract['id']}]",
                    "consumer dependency graph omits contract producer",
                    {"producer": producer, "consumer": consumer},
                )
    return analysis
