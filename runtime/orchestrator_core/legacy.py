from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .protocol import ProtocolError

_STAGE_HEADING = re.compile(r"^### (S[0-9]{2}) — (.+)$")
_FIELD = re.compile(r"^- ([^:]+): (.*)$")


@dataclass(frozen=True)
class LegacyStage:
    stage_id: str
    title: str
    status: str
    revision: int
    depends_on: tuple[str, ...]
    details: str
    review: str
    human_review: str
    human_review_revision: int
    human_review_status: str
    human_review_review: str


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ProtocolError("legacy.frontmatter", "start delimiter missing")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ProtocolError("legacy.frontmatter", "end delimiter missing") from error
    result: dict[str, str] = {}
    for line in lines[1:end]:
        if not line or ":" not in line:
            raise ProtocolError("legacy.frontmatter", "expected key: value", line)
        key, value = line.split(":", 1)
        key = key.strip()
        if key in result:
            raise ProtocolError(f"legacy.{key}", "duplicate field")
        result[key] = value.strip()
    return result


def _integer(value: str, field: str) -> int:
    if re.fullmatch(r"[0-9]+", value) is None:
        raise ProtocolError(field, "must be a non-negative integer", value)
    return int(value)


def _dependencies(value: str) -> tuple[str, ...]:
    if value in {"none", "[]", ""}:
        return ()
    values = tuple(part.strip() for part in value.strip("[]").split(",") if part.strip())
    for item in values:
        if re.fullmatch(r"S[0-9]{2}", item) is None:
            raise ProtocolError("legacy.Depends on", "invalid stage identifier", item)
    return values


def parse_legacy_plan(path: Path) -> dict[str, Any]:
    """Parse the stable subset of v5 plan.md without guessing absent semantics."""

    text = path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(text)
    status = frontmatter.get("status", "discovery")
    current_stage = frontmatter.get("current_stage", "none")
    lines = text.splitlines()
    headings = [index for index, line in enumerate(lines) if line == "## Stage map"]
    if not headings:
        return {
            "status": status,
            "current_stage": None if current_stage == "none" else current_stage,
            "stages": [],
            "requires_analysis_migration": True,
        }
    if len(headings) != 1:
        raise ProtocolError("legacy.Stage map", "expected exactly one section")
    start = headings[0] + 1
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    stages: list[LegacyStage] = []
    index = start
    while index < end:
        if not lines[index]:
            index += 1
            continue
        match = _STAGE_HEADING.fullmatch(lines[index])
        if match is None:
            raise ProtocolError("legacy.Stage map", "expected stage heading", lines[index])
        stage_id, title = match.groups()
        index += 1
        fields: dict[str, str] = {}
        while index < end and not lines[index].startswith("### "):
            line = lines[index]
            index += 1
            if not line:
                continue
            field_match = _FIELD.fullmatch(line)
            if field_match is None:
                raise ProtocolError(f"legacy.{stage_id}", "expected '- Field: value'", line)
            key, value = field_match.groups()
            if key in fields:
                raise ProtocolError(f"legacy.{stage_id}.{key}", "duplicate field")
            fields[key] = value
        required = {"Status", "Revision", "Depends on", "Details", "Review"}
        missing = sorted(required - set(fields))
        if missing:
            raise ProtocolError(f"legacy.{stage_id}", "missing fields", missing)
        number = int(stage_id[1:])
        details = fields["Details"]
        slug_match = re.fullmatch(rf"stages/{number:02d}-([a-z0-9]+(?:-[a-z0-9]+)*)\.md", details)
        if slug_match is None:
            raise ProtocolError(f"legacy.{stage_id}.Details", "non-canonical path", details)
        slug = slug_match.group(1)
        stages.append(
            LegacyStage(
                stage_id=stage_id,
                title=title,
                status=fields["Status"],
                revision=_integer(fields["Revision"], f"legacy.{stage_id}.Revision"),
                depends_on=_dependencies(fields["Depends on"]),
                details=details,
                review=fields["Review"],
                human_review=fields.get("Human review", f"stages/{number:02d}-{slug}.human-review.md"),
                human_review_revision=_integer(fields.get("Human review revision", "0"), f"legacy.{stage_id}.Human review revision"),
                human_review_status=fields.get("Human review status", "PENDING"),
                human_review_review=fields.get("Human review review", f"reviews/{number:02d}-human-review.md"),
            )
        )
    for expected, stage in enumerate(stages, start=1):
        if stage.stage_id != f"S{expected:02d}":
            raise ProtocolError("legacy.Stage map", "stages must be contiguous and ordered", stage.stage_id)
        valid_dependencies = {item.stage_id for item in stages[: expected - 1]}
        invalid = sorted(set(stage.depends_on) - valid_dependencies)
        if invalid:
            raise ProtocolError(f"legacy.{stage.stage_id}.Depends on", "must reference earlier stages", invalid)
    return {
        "status": status,
        "current_stage": None if current_stage == "none" else current_stage,
        "stages": [stage.__dict__ for stage in stages],
        "requires_analysis_migration": True,
    }
