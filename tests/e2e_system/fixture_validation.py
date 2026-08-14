from __future__ import annotations

from pathlib import Path
import re


def replace_required(path: Path, source: str, replacement: str, expected_count: int = 1) -> None:
    if not source or source == replacement:
        raise AssertionError(f"invalid required replacement in {path}: source must be non-empty and differ from replacement")
    content = path.read_text(encoding="utf-8")
    actual_count = content.count(source)
    if actual_count != expected_count:
        raise AssertionError(f"required fragment count mismatch in {path}: expected {expected_count}, found {actual_count}; fragment={source!r}")
    result = content.replace(source, replacement)
    if replacement:
        expected_result_count = content.count(replacement) + expected_count
        actual_result_count = result.count(replacement)
        if actual_result_count != expected_result_count:
            raise AssertionError(f"replacement result count mismatch in {path}: expected {expected_result_count}, found {actual_result_count}; replacement={replacement!r}")
    elif result == content or source in result:
        raise AssertionError(f"replacement result missing in {path}: required fragment was not removed; fragment={source!r}")
    path.write_text(result, encoding="utf-8")


def parse_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise AssertionError(f"frontmatter start missing in {path}")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise AssertionError(f"frontmatter end missing in {path}") from error
    fields = {}
    for line in lines[1:end]:
        if not line or ":" not in line:
            raise AssertionError(f"invalid frontmatter line in {path}: {line!r}")
        key, value = line.split(":", 1)
        if key in fields:
            raise AssertionError(f"duplicate frontmatter field in {path}: {key}")
        fields[key] = value.strip()
    return fields


def parse_stage_map(plan: Path) -> dict[str, dict[str, str]]:
    stages: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    in_stage_map = False
    for line in plan.read_text(encoding="utf-8").splitlines():
        if line == "## Stage map":
            in_stage_map = True
            continue
        if in_stage_map and line.startswith("## "):
            break
        if not in_stage_map:
            continue
        heading = re.match(r"^### (S\d{2})\b", line)
        if heading:
            stage_id = heading.group(1)
            if stage_id in stages:
                raise AssertionError(f"duplicate stage map entry in {plan}: {stage_id}")
            current = {}
            stages[stage_id] = current
        elif current is not None and line.startswith("- ") and ": " in line:
            key, value = line[2:].split(": ", 1)
            if key in current:
                raise AssertionError(f"duplicate stage field in {plan}: {key}")
            current[key] = value
    return stages


def assert_fixture_state(plan: Path, workflow_status: str, current_stage: str, stage_id: str, stage_fields: dict[str, str], artifact_path: Path | None = None, artifact_fields: dict[str, str] | None = None, review_path: Path | None = None, review_fields: dict[str, str] | None = None) -> None:
    plan_fields = parse_frontmatter(plan)
    expected_plan_fields = {"status": workflow_status, "current_stage": current_stage}
    _assert_fields(plan, plan_fields, expected_plan_fields)
    stages = parse_stage_map(plan)
    if stage_id not in stages:
        raise AssertionError(f"stage map entry missing in {plan}: {stage_id}")
    _assert_fields(plan, stages[stage_id], stage_fields)
    if artifact_path is not None:
        if artifact_fields is None:
            raise AssertionError(f"artifact fields missing for fixture validation: {artifact_path}")
        artifact_frontmatter = parse_frontmatter(artifact_path)
        _assert_fields(artifact_path, artifact_frontmatter, {"stage": stage_id})
        _assert_fields(artifact_path, artifact_frontmatter, artifact_fields)
    if review_path is not None:
        if review_fields is None:
            raise AssertionError(f"review fields missing for fixture validation: {review_path}")
        review_frontmatter = parse_frontmatter(review_path)
        _assert_fields(review_path, review_frontmatter, {"stage": stage_id})
        _assert_fields(review_path, review_frontmatter, review_fields)


def _assert_fields(path: Path, actual: dict[str, str], expected: dict[str, str]) -> None:
    mismatches = {key: {"expected": value, "actual": actual.get(key)} for key, value in expected.items() if actual.get(key) != value}
    if mismatches:
        raise AssertionError(f"fixture state mismatch in {path}: {mismatches}")
