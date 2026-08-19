#!/usr/bin/env python3

import json
from pathlib import Path
import re
from typing import Any


CATALOG_PATH = Path(__file__).with_name("failure_scenarios.json")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_IDS = (
    "malformed-compact-result",
    "corrupt-partial-plan",
    "stale-artifact",
    "mismatched-artifact",
    "task-timeout",
    "task-cancellation",
    "permission-denial",
    "repeating-revise-no-progress",
    "concurrent-resume",
    "repository-prompt-injection",
    "shell-mutation",
    "mcp-mutation",
)
TEST_LAYERS = frozenset({"deterministic-unit", "live-transition-checkpoint", "none"})
COVERAGE_VALUES = frozenset({"covered", "partial", "uncovered"})
ROADMAP_PHASES = frozenset({f"phase-{number}" for number in range(10)})
SECURITY_IDS = frozenset({"permission-denial", "repository-prompt-injection", "shell-mutation", "mcp-mutation"})
CHECKPOINT_ONLY_IDS = frozenset({"stale-artifact"})
SCENARIO_FIELDS = frozenset({"id", "description", "observable_failure", "test_layer", "coverage", "existing_test_path", "target_roadmap_phase", "defer_reason"})


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        catalog = json.load(source)
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: object, repository_root: Path = REPOSITORY_ROOT) -> None:
    if not isinstance(catalog, dict) or set(catalog) != {"schema_version", "scenarios"}:
        raise ValueError("catalog must contain exactly schema_version and scenarios")
    if catalog["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    scenarios = catalog["scenarios"]
    if not isinstance(scenarios, list):
        raise ValueError("scenarios must be a list")
    ids = [scenario.get("id") if isinstance(scenario, dict) else None for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("scenario IDs must be unique")
    if tuple(ids) != REQUIRED_IDS:
        raise ValueError(f"scenario IDs must be complete and ordered: {REQUIRED_IDS}")
    for scenario in scenarios:
        _validate_scenario(scenario, repository_root)


def _validate_scenario(scenario: object, repository_root: Path) -> None:
    if not isinstance(scenario, dict) or set(scenario) != SCENARIO_FIELDS:
        raise ValueError("each scenario must contain exactly the catalog scenario fields")
    scenario_id = scenario["id"]
    for field in ("id", "description", "observable_failure"):
        if not isinstance(scenario[field], str) or not scenario[field].strip():
            raise ValueError(f"{scenario_id}: {field} must be a non-empty string")
    if scenario["test_layer"] not in TEST_LAYERS:
        raise ValueError(f"{scenario_id}: invalid test_layer")
    if scenario["coverage"] not in COVERAGE_VALUES:
        raise ValueError(f"{scenario_id}: invalid coverage")
    if scenario["target_roadmap_phase"] not in ROADMAP_PHASES:
        raise ValueError(f"{scenario_id}: invalid target_roadmap_phase")
    path = scenario["existing_test_path"]
    reason = scenario["defer_reason"]
    if scenario["coverage"] == "covered":
        if scenario["test_layer"] == "none" or not isinstance(path, str) or not path.startswith("tests/"):
            raise ValueError(f"{scenario_id}: covered scenario requires an existing test path and layer")
        if not valid_test_path(repository_root, path):
            raise ValueError(f"{scenario_id}: covered test path does not exist: {path}")
        if reason is not None:
            raise ValueError(f"{scenario_id}: covered scenario cannot have defer_reason")
    else:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{scenario_id}: non-covered scenario requires defer_reason")
        if scenario["coverage"] == "uncovered" and (scenario["test_layer"] != "none" or path is not None):
            raise ValueError(f"{scenario_id}: uncovered scenario cannot claim a test")
        if scenario["coverage"] == "partial":
            if scenario["test_layer"] == "none" or not isinstance(path, str) or not valid_test_path(repository_root, path):
                raise ValueError(f"{scenario_id}: partial scenario requires an existing test path and layer")
    if scenario_id in SECURITY_IDS and (scenario["coverage"] != "uncovered" or scenario["target_roadmap_phase"] != "phase-1" or path is not None):
        raise ValueError(f"{scenario_id}: phase-1 security scenario must remain honestly uncovered")
    if scenario_id in CHECKPOINT_ONLY_IDS and (scenario["coverage"] != "partial" or scenario["test_layer"] != "live-transition-checkpoint"):
        raise ValueError(f"{scenario_id}: checkpoint coverage cannot claim a full journey")
    if scenario["test_layer"] == "live-transition-checkpoint" and scenario["coverage"] != "partial":
        raise ValueError(f"{scenario_id}: live transition checkpoint must be partial coverage")


def valid_test_path(repository_root: Path, value: str) -> bool:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or re.fullmatch(r"test[-_].+\.py", relative.name) is None:
        return False
    tests_root = (repository_root / "tests").resolve()
    candidate = repository_root / relative
    resolved = candidate.resolve()
    if tests_root not in resolved.parents or not resolved.is_file():
        return False
    current = repository_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    return True


if __name__ == "__main__":
    load_catalog()
    print("failure scenario catalog valid")
