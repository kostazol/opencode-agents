from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping, NoReturn

ANALYSIS_SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 1

ID_PATTERNS = {
    "REQ": re.compile(r"^REQ-[0-9]{3}$"),
    "NFR": re.compile(r"^NFR-[0-9]{3}$"),
    "DEC": re.compile(r"^DEC-[0-9]{3}$"),
    "CON": re.compile(r"^CON-[0-9]{3}$"),
    "AC": re.compile(r"^AC-[0-9]{3}$"),
    "SCN": re.compile(r"^SCN-[0-9]{3}$"),
}
STAGE_ID = re.compile(r"^S([0-9]{2})$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

CHANGE_SURFACES = frozenset(
    {
        "api",
        "data",
        "ui",
        "infra",
        "security",
        "migration",
        "background",
        "library",
    }
)
NFR_CATEGORIES = frozenset(
    {
        "performance-capacity",
        "availability-recovery",
        "security-privacy-compliance",
        "data-integrity-concurrency",
        "compatibility-migration",
        "observability-support",
        "rollout-rollback",
        "accessibility-localization",
        "cost-resources",
    }
)
SURFACE_NFR = {
    "api": {
        "performance-capacity",
        "availability-recovery",
        "security-privacy-compliance",
        "compatibility-migration",
        "observability-support",
    },
    "data": {
        "data-integrity-concurrency",
        "compatibility-migration",
        "availability-recovery",
        "observability-support",
    },
    "ui": {
        "performance-capacity",
        "accessibility-localization",
        "compatibility-migration",
    },
    "infra": {
        "availability-recovery",
        "observability-support",
        "rollout-rollback",
        "cost-resources",
        "security-privacy-compliance",
    },
    "security": {"security-privacy-compliance", "observability-support"},
    "migration": {
        "compatibility-migration",
        "data-integrity-concurrency",
        "rollout-rollback",
        "availability-recovery",
    },
    "background": {
        "availability-recovery",
        "data-integrity-concurrency",
        "observability-support",
        "cost-resources",
    },
    "library": {"compatibility-migration"},
}


class ProtocolError(ValueError):
    """A durable artifact violates the versioned workflow contract."""

    def __init__(self, field: str, message: str, value: Any = None):
        self.field = field
        self.value = value
        detail = f"{field}: {message}"
        if value is not None:
            detail += f"; value={value!r}"
        super().__init__(detail)


def _reject_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError(key, "duplicate JSON key")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as source:
            value = json.load(source, object_pairs_hook=_reject_duplicate_object)
    except ProtocolError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProtocolError(str(path), f"invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ProtocolError(str(path), "root must be an object", type(value).__name__)
    return value


def _fail(field: str, message: str, value: Any = None) -> NoReturn:
    raise ProtocolError(field, message, value)


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(field, "must be an object", type(value).__name__)
    return value


def _array(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(field, "must be an array", type(value).__name__)
    return value


def _string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        _fail(field, "must be a non-empty string", value)
    return value.strip() if not allow_empty else value


def _string_array(value: Any, field: str) -> list[str]:
    result = [_string(item, f"{field}[{index}]") for index, item in enumerate(_array(value, field))]
    if len(result) != len(set(result)):
        _fail(field, "must not contain duplicates", result)
    return result


def _required(obj: Mapping[str, Any], fields: Iterable[str], prefix: str) -> None:
    missing = sorted(set(fields) - set(obj))
    if missing:
        _fail(prefix, "missing required fields", missing)


def _only(obj: Mapping[str, Any], fields: Iterable[str], prefix: str) -> None:
    unknown = sorted(set(obj) - set(fields))
    if unknown:
        _fail(prefix, "unexpected fields", unknown)


def _id(value: Any, kind: str, field: str) -> str:
    text = _string(value, field)
    if ID_PATTERNS[kind].fullmatch(text) is None:
        _fail(field, f"must match {kind}-NNN", text)
    return text


def _stage_id(value: Any, field: str) -> str:
    text = _string(value, field)
    if STAGE_ID.fullmatch(text) is None:
        _fail(field, "must match SNN", text)
    return text


def _index_by_id(items: list[dict[str, Any]], kind: str, field: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        item_id = _id(item.get("id"), kind, f"{field}[{index}].id")
        if item_id in result:
            _fail(field, "duplicate identifier", item_id)
        result[item_id] = item
    return result


def canonical_relative_path(value: Any, field: str, expected_prefix: str | None = None) -> str:
    text = _string(value, field)
    if "\\" in text:
        _fail(field, "must use POSIX separators", text)
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        _fail(field, "must be a canonical relative path", text)
    normalized = path.as_posix()
    if normalized != text:
        _fail(field, "must already be normalized", text)
    if expected_prefix and not normalized.startswith(expected_prefix):
        _fail(field, f"must start with {expected_prefix}", text)
    return normalized


def required_nfr_categories(change_surfaces: Iterable[str]) -> set[str]:
    categories: set[str] = set()
    for surface in change_surfaces:
        categories.update(SURFACE_NFR[surface])
    return categories


def validate_analysis(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a normalized deep copy of analysis.json schema v1."""

    root = _object(deepcopy(dict(payload)), "analysis")
    fields = {
        "schema_version",
        "request",
        "change_surfaces",
        "requirements",
        "nfrs",
        "decisions",
        "contracts",
        "acceptance",
        "scenarios",
        "nfr_applicability",
        "stages",
        "assumptions",
        "non_goals",
    }
    _required(root, fields, "analysis")
    _only(root, fields, "analysis")
    if root["schema_version"] != ANALYSIS_SCHEMA_VERSION:
        _fail("schema_version", f"must be {ANALYSIS_SCHEMA_VERSION}", root["schema_version"])

    request = _object(root["request"], "request")
    _required(request, {"summary", "outcomes"}, "request")
    _only(request, {"summary", "outcomes"}, "request")
    request["summary"] = _string(request["summary"], "request.summary")
    request["outcomes"] = _string_array(request["outcomes"], "request.outcomes")
    if not request["outcomes"]:
        _fail("request.outcomes", "must contain at least one outcome")

    surfaces = _string_array(root["change_surfaces"], "change_surfaces")
    invalid_surfaces = sorted(set(surfaces) - CHANGE_SURFACES)
    if invalid_surfaces:
        _fail("change_surfaces", "contains unsupported values", invalid_surfaces)
    root["change_surfaces"] = surfaces

    collections: dict[str, list[dict[str, Any]]] = {}
    for name in ("requirements", "nfrs", "decisions", "contracts", "acceptance", "scenarios", "nfr_applicability", "stages"):
        values = _array(root[name], name)
        collections[name] = [_object(item, f"{name}[{index}]") for index, item in enumerate(values)]
        root[name] = collections[name]

    requirements = _index_by_id(collections["requirements"], "REQ", "requirements")
    nfrs = _index_by_id(collections["nfrs"], "NFR", "nfrs")
    decisions = _index_by_id(collections["decisions"], "DEC", "decisions")
    contracts = _index_by_id(collections["contracts"], "CON", "contracts")
    acceptance = _index_by_id(collections["acceptance"], "AC", "acceptance")
    scenarios = _index_by_id(collections["scenarios"], "SCN", "scenarios")
    del decisions

    stages: dict[str, dict[str, Any]] = {}
    ordered_stage_ids: list[str] = []
    stage_fields = {
        "id",
        "title",
        "slug",
        "depends_on",
        "requirements",
        "nfrs",
        "contracts_consumed",
        "contracts_produced",
        "affected_area",
        "risks",
    }
    for index, stage in enumerate(collections["stages"], start=1):
        prefix = f"stages[{index - 1}]"
        _required(stage, stage_fields, prefix)
        _only(stage, stage_fields, prefix)
        stage_id = _stage_id(stage["id"], f"{prefix}.id")
        expected_id = f"S{index:02d}"
        if stage_id != expected_id:
            _fail(f"{prefix}.id", "stages must be contiguous and ordered", stage_id)
        if stage_id in stages:
            _fail("stages", "duplicate stage", stage_id)
        stage["title"] = _string(stage["title"], f"{prefix}.title")
        slug = _string(stage["slug"], f"{prefix}.slug")
        if SLUG.fullmatch(slug) is None:
            _fail(f"{prefix}.slug", "must be lower kebab-case", slug)
        stage["depends_on"] = [_stage_id(value, f"{prefix}.depends_on") for value in _string_array(stage["depends_on"], f"{prefix}.depends_on")]
        invalid_dependencies = [value for value in stage["depends_on"] if value not in ordered_stage_ids]
        if invalid_dependencies:
            _fail(f"{prefix}.depends_on", "dependencies must reference earlier stages", invalid_dependencies)
        for key, ids, valid, kind in (
            ("requirements", stage["requirements"], requirements, "REQ"),
            ("nfrs", stage["nfrs"], nfrs, "NFR"),
            ("contracts_consumed", stage["contracts_consumed"], contracts, "CON"),
            ("contracts_produced", stage["contracts_produced"], contracts, "CON"),
        ):
            normalized = [_id(value, kind, f"{prefix}.{key}") for value in _string_array(ids, f"{prefix}.{key}")]
            missing = sorted(set(normalized) - set(valid))
            if missing:
                _fail(f"{prefix}.{key}", "references unknown identifiers", missing)
            stage[key] = normalized
        stage["affected_area"] = _string(stage["affected_area"], f"{prefix}.affected_area")
        stage["risks"] = _string_array(stage["risks"], f"{prefix}.risks")
        stages[stage_id] = stage
        ordered_stage_ids.append(stage_id)
    if not stages:
        _fail("stages", "must contain at least one stage")

    link_fields = {"id", "text", "stage", "acceptance", "scenarios"}
    for req_id, item in requirements.items():
        prefix = f"requirements[{req_id}]"
        _required(item, link_fields, prefix)
        _only(item, link_fields, prefix)
        item["text"] = _string(item["text"], f"{prefix}.text")
        stage_id = _stage_id(item["stage"], f"{prefix}.stage")
        if stage_id not in stages:
            _fail(f"{prefix}.stage", "references unknown stage", stage_id)
        item["acceptance"] = [_id(value, "AC", f"{prefix}.acceptance") for value in _string_array(item["acceptance"], f"{prefix}.acceptance")]
        item["scenarios"] = [_id(value, "SCN", f"{prefix}.scenarios") for value in _string_array(item["scenarios"], f"{prefix}.scenarios")]
        if not item["acceptance"] or not item["scenarios"]:
            _fail(prefix, "requires at least one acceptance criterion and scenario")
        if set(item["acceptance"]) - set(acceptance):
            _fail(f"{prefix}.acceptance", "references unknown acceptance", sorted(set(item["acceptance"]) - set(acceptance)))
        if set(item["scenarios"]) - set(scenarios):
            _fail(f"{prefix}.scenarios", "references unknown scenarios", sorted(set(item["scenarios"]) - set(scenarios)))
        if req_id not in stages[stage_id]["requirements"]:
            _fail(prefix, "owning stage does not list requirement", stage_id)

    nfr_fields = {"id", "text", "category", "stage", "acceptance", "scenarios"}
    for nfr_id, item in nfrs.items():
        prefix = f"nfrs[{nfr_id}]"
        _required(item, nfr_fields, prefix)
        _only(item, nfr_fields, prefix)
        item["text"] = _string(item["text"], f"{prefix}.text")
        category = _string(item["category"], f"{prefix}.category")
        if category not in NFR_CATEGORIES:
            _fail(f"{prefix}.category", "unsupported NFR category", category)
        stage_id = _stage_id(item["stage"], f"{prefix}.stage")
        if stage_id not in stages:
            _fail(f"{prefix}.stage", "references unknown stage", stage_id)
        item["acceptance"] = [_id(value, "AC", f"{prefix}.acceptance") for value in _string_array(item["acceptance"], f"{prefix}.acceptance")]
        item["scenarios"] = [_id(value, "SCN", f"{prefix}.scenarios") for value in _string_array(item["scenarios"], f"{prefix}.scenarios")]
        if not item["acceptance"]:
            _fail(prefix, "required NFR needs observable acceptance")
        if set(item["acceptance"]) - set(acceptance) or set(item["scenarios"]) - set(scenarios):
            _fail(prefix, "references unknown acceptance or scenarios")
        if nfr_id not in stages[stage_id]["nfrs"]:
            _fail(prefix, "owning stage does not list NFR", stage_id)

    acceptance_fields = {"id", "text", "stage", "verification"}
    for ac_id, item in acceptance.items():
        prefix = f"acceptance[{ac_id}]"
        _required(item, acceptance_fields, prefix)
        _only(item, acceptance_fields, prefix)
        item["text"] = _string(item["text"], f"{prefix}.text")
        item["verification"] = _string(item["verification"], f"{prefix}.verification")
        stage_id = _stage_id(item["stage"], f"{prefix}.stage")
        if stage_id not in stages:
            _fail(f"{prefix}.stage", "references unknown stage", stage_id)

    scenario_fields = {"id", "text", "stage", "requirements", "expected"}
    for scenario_id, item in scenarios.items():
        prefix = f"scenarios[{scenario_id}]"
        _required(item, scenario_fields, prefix)
        _only(item, scenario_fields, prefix)
        item["text"] = _string(item["text"], f"{prefix}.text")
        item["expected"] = _string(item["expected"], f"{prefix}.expected")
        stage_id = _stage_id(item["stage"], f"{prefix}.stage")
        if stage_id not in stages:
            _fail(f"{prefix}.stage", "references unknown stage", stage_id)
        linked = _string_array(item["requirements"], f"{prefix}.requirements")
        for value in linked:
            kind = value.split("-", 1)[0]
            if kind not in {"REQ", "NFR"}:
                _fail(f"{prefix}.requirements", "must reference REQ or NFR", value)
            _id(value, kind, f"{prefix}.requirements")
            if value not in requirements and value not in nfrs:
                _fail(f"{prefix}.requirements", "references unknown requirement", value)
        if not linked:
            _fail(f"{prefix}.requirements", "must link at least one requirement")
        item["requirements"] = linked

    contract_fields = {"id", "text", "producer", "consumers", "external", "terminal"}
    for contract_id, item in contracts.items():
        prefix = f"contracts[{contract_id}]"
        _required(item, contract_fields, prefix)
        _only(item, contract_fields, prefix)
        item["text"] = _string(item["text"], f"{prefix}.text")
        if not isinstance(item["external"], bool) or not isinstance(item["terminal"], bool):
            _fail(prefix, "external and terminal must be booleans")
        producer = item["producer"]
        if producer is not None:
            producer = _stage_id(producer, f"{prefix}.producer")
            if producer not in stages:
                _fail(f"{prefix}.producer", "references unknown stage", producer)
        if item["external"] and producer is not None:
            _fail(prefix, "external contract cannot have an internal producer")
        if not item["external"] and producer is None:
            _fail(prefix, "internal contract requires a producer")
        consumers = [_stage_id(value, f"{prefix}.consumers") for value in _string_array(item["consumers"], f"{prefix}.consumers")]
        missing = sorted(set(consumers) - set(stages))
        if missing:
            _fail(f"{prefix}.consumers", "references unknown stages", missing)
        if not consumers and not item["terminal"]:
            _fail(prefix, "contract without consumers must be terminal")
        item["producer"] = producer
        item["consumers"] = consumers
        if producer and contract_id not in stages[producer]["contracts_produced"]:
            _fail(prefix, "producer stage does not list contract", producer)
        for consumer in consumers:
            if contract_id not in stages[consumer]["contracts_consumed"]:
                _fail(prefix, "consumer stage does not list contract", consumer)

    nfr_applicable_fields = {"category", "status", "evidence", "owner", "acceptance"}
    applicability: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(collections["nfr_applicability"]):
        prefix = f"nfr_applicability[{index}]"
        _required(item, nfr_applicable_fields, prefix)
        _only(item, nfr_applicable_fields, prefix)
        category = _string(item["category"], f"{prefix}.category")
        if category not in NFR_CATEGORIES:
            _fail(f"{prefix}.category", "unsupported category", category)
        if category in applicability:
            _fail("nfr_applicability", "duplicate category", category)
        status = _string(item["status"], f"{prefix}.status")
        if status not in {"required", "not_applicable", "deferred"}:
            _fail(f"{prefix}.status", "unsupported status", status)
        item["evidence"] = _string(item["evidence"], f"{prefix}.evidence")
        owner = item["owner"]
        if owner is not None:
            owner = _stage_id(owner, f"{prefix}.owner")
            if owner not in stages:
                _fail(f"{prefix}.owner", "references unknown stage", owner)
        linked_acceptance = [_id(value, "AC", f"{prefix}.acceptance") for value in _string_array(item["acceptance"], f"{prefix}.acceptance")]
        if set(linked_acceptance) - set(acceptance):
            _fail(f"{prefix}.acceptance", "references unknown acceptance", sorted(set(linked_acceptance) - set(acceptance)))
        if status == "required" and (owner is None or not linked_acceptance):
            _fail(prefix, "required category needs owner and acceptance")
        if status != "required" and linked_acceptance:
            _fail(prefix, "non-required category cannot claim acceptance")
        item["owner"] = owner
        item["acceptance"] = linked_acceptance
        applicability[category] = item
    missing_categories = sorted(required_nfr_categories(surfaces) - set(applicability))
    if missing_categories:
        _fail("nfr_applicability", "missing categories implied by change surfaces", missing_categories)

    root["assumptions"] = _string_array(root["assumptions"], "assumptions")
    root["non_goals"] = _string_array(root["non_goals"], "non_goals")
    return root


def analysis_stage_index(analysis: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    validated = validate_analysis(analysis)
    return {stage["id"]: stage for stage in validated["stages"]}


def affected_stage_closure(analysis: Mapping[str, Any], seeds: Iterable[str]) -> list[str]:
    """Return the smallest ordered stage set affected by stage/contract dependencies."""

    validated = validate_analysis(analysis)
    stages = {stage["id"]: stage for stage in validated["stages"]}
    seed_set = set(seeds)
    unknown = sorted(seed_set - set(stages))
    if unknown:
        _fail("affected_stages", "unknown seed stages", unknown)
    contracts = {item["id"]: item for item in validated["contracts"]}
    affected = set(seed_set)
    changed = True
    while changed:
        changed = False
        produced = {
            contract_id
            for stage_id in affected
            for contract_id in stages[stage_id]["contracts_produced"]
        }
        contract_consumers = {
            consumer
            for contract_id in produced
            for consumer in contracts[contract_id]["consumers"]
        }
        for stage_id, stage in stages.items():
            if stage_id in affected:
                continue
            if set(stage["depends_on"]) & affected or stage_id in contract_consumers:
                affected.add(stage_id)
                changed = True
    return [stage["id"] for stage in validated["stages"] if stage["id"] in affected]
