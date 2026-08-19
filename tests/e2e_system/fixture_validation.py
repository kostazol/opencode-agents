from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re
from typing import Callable, NoReturn

from workflow_invariants import validate_workflow_invariants


STAGE_ID = re.compile(r"^S(\d{2})$")
STAGE_MAP_FIELDS = (
    "Status",
    "Revision",
    "Depends on",
    "Affected area",
    "Primary risks",
    "Consumes",
    "Produces",
    "Details",
    "Review",
    "Human review",
    "Human review revision",
    "Human review status",
    "Human review review",
)
STAGE_MAP_OPTIONAL_FIELDS = (
    "Correction source revision",
    "Human review correction source revision",
    "Human review mismatch source revision",
)


@dataclass(frozen=True)
class PlanFrontmatter:
    status: str
    current_stage: str


@dataclass(frozen=True)
class StageMapEntry:
    stage_id: str
    title: str
    status: str
    revision: int
    depends_on: str
    affected_area: str
    primary_risks: str
    consumes: str
    produces: str
    details: str
    review: str
    human_review: str
    human_review_revision: int
    human_review_status: str
    human_review_review: str
    correction_source_revision: int | None = None
    human_review_correction_source_revision: int | None = None
    human_review_mismatch_source_revision: int | None = None


@dataclass(frozen=True)
class TechnicalStage:
    path: Path
    stage_id: str
    status: str
    revision: int


@dataclass(frozen=True)
class TechnicalReview:
    path: Path
    stage_id: str
    stage_revision: int
    status: str


@dataclass(frozen=True)
class HumanReview:
    path: Path
    stage_id: str
    status: str
    revision: int
    source_revision: int


@dataclass(frozen=True)
class HumanReviewReview:
    path: Path
    stage_id: str
    stage_revision: int
    source_revision: int
    status: str


@dataclass(frozen=True)
class QuestionState:
    path: Path
    status: str
    revision: int
    answers: tuple[str, ...]


@dataclass(frozen=True)
class FeedbackEntry:
    revision: int
    status: str
    remarks: str
    affected_stages: tuple[str, ...] | None
    questions: str


@dataclass(frozen=True)
class FeedbackState:
    path: Path
    latest_revision: int
    mode: str
    entries: tuple[FeedbackEntry, ...]


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
        _fail(path, "frontmatter", lines[0] if lines else None, "start delimiter missing")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise AssertionError(f"fixture parse error: path={path}; field=frontmatter; value=None; end delimiter missing") from error
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if not line or ":" not in line:
            _fail(path, "frontmatter line", line, "expected key: value")
        key, value = line.split(":", 1)
        if not key or key != key.strip():
            _fail(path, "frontmatter field", key, "invalid field name")
        if key in fields:
            _fail(path, key, value.strip(), "duplicate field")
        fields[key] = value.strip()
    return fields


def parse_plan_frontmatter(path: Path) -> PlanFrontmatter:
    fields = parse_frontmatter(path)
    _require_fields(path, fields, ("status", "current_stage"))
    _choice(path, "status", fields["status"], ("discovery", "waiting-answers", "waiting-approval", "waiting-map-approval", "planning", "human-reviewing", "waiting-plan-approval", "ready", "blocked"))
    current_stage = fields["current_stage"]
    if current_stage != "none":
        _stage_number(path, "current_stage", current_stage)
    return PlanFrontmatter(fields["status"], current_stage)


def parse_stage_map(path: Path) -> dict[str, StageMapEntry]:
    lines = path.read_text(encoding="utf-8").splitlines()
    headings = [index for index, line in enumerate(lines) if line == "## Stage map"]
    if len(headings) != 1:
        _fail(path, "Stage map", len(headings), "expected exactly one section")
    start = headings[0] + 1
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    stages: dict[str, StageMapEntry] = {}
    index = start
    while index < end:
        line = lines[index]
        if not line:
            index += 1
            continue
        heading = re.fullmatch(r"### (S\d{2}) — (.+)", line)
        if not heading:
            _fail(path, "Stage map line", line, "expected stage heading")
        stage_id, title = heading.groups()
        _stage_number(path, "stage_id", stage_id)
        if stage_id in stages:
            _fail(path, "stage_id", stage_id, "duplicate stage map entry")
        index += 1
        fields: dict[str, str] = {}
        while index < end and not lines[index].startswith("### "):
            field_line = lines[index]
            index += 1
            if not field_line:
                continue
            match = re.fullmatch(r"- ([^:]+): (.*)", field_line)
            if not match:
                _fail(path, f"{stage_id} field", field_line, "expected '- Field: value'")
            key, value = match.groups()
            if key in fields:
                _fail(path, f"{stage_id}.{key}", value, "duplicate field")
            fields[key] = value
        _require_fields(path, fields, STAGE_MAP_FIELDS, stage_id)
        unknown = sorted(set(fields) - set(STAGE_MAP_FIELDS) - set(STAGE_MAP_OPTIONAL_FIELDS))
        if unknown:
            _fail(path, f"{stage_id}.fields", unknown, "unexpected stage map fields")
        revision = _integer(path, f"{stage_id}.Revision", fields["Revision"])
        human_revision = _integer(path, f"{stage_id}.Human review revision", fields["Human review revision"])
        _choice(path, f"{stage_id}.Status", fields["Status"], ("PROPOSED", "PLANNING", "REVIEW", "PASS", "BLOCKED", "MAP_CHANGE_REQUIRED"))
        _choice(path, f"{stage_id}.Human review status", fields["Human review status"], ("PENDING", "REVIEW", "PASS"))
        number = _stage_number(path, "stage_id", stage_id)
        details = fields["Details"]
        details_match = re.fullmatch(rf"stages/{number:02d}-([a-z0-9]+(?:-[a-z0-9]+)*)\.md", details)
        if not details_match:
            _fail(path, f"{stage_id}.Details", details, "non-canonical indexed path")
        slug = details_match.group(1)
        expected_paths = {
            "Review": f"reviews/{number:02d}.md",
            "Human review": f"stages/{number:02d}-{slug}.human-review.md",
            "Human review review": f"reviews/{number:02d}-human-review.md",
        }
        for field, expected in expected_paths.items():
            if fields[field] != expected:
                _fail(path, f"{stage_id}.{field}", fields[field], f"expected {expected!r}")
        optional_revisions = tuple(_integer(path, f"{stage_id}.{field}", fields[field]) if field in fields else None for field in STAGE_MAP_OPTIONAL_FIELDS)
        stages[stage_id] = StageMapEntry(stage_id, title, fields["Status"], revision, fields["Depends on"], fields["Affected area"], fields["Primary risks"], fields["Consumes"], fields["Produces"], details, fields["Review"], fields["Human review"], human_revision, fields["Human review status"], fields["Human review review"], *optional_revisions)
    if not stages:
        _fail(path, "Stage map", None, "no stage entries")
    expected_ids = [f"S{index:02d}" for index in range(1, len(stages) + 1)]
    if list(stages) != expected_ids:
        _fail(path, "Stage map identities", list(stages), f"expected ordered identities {expected_ids!r}")
    current_stage = parse_plan_frontmatter(path).current_stage
    if current_stage != "none" and current_stage not in stages:
        _fail(path, "current_stage", current_stage, "stage map entry missing")
    return stages


def parse_stage_map_entry(path: Path, stage_id: str) -> StageMapEntry:
    _stage_number(path, "requested stage_id", stage_id)
    stages = parse_stage_map(path)
    if stage_id not in stages:
        _fail(path, "stage_id", stage_id, "stage map entry missing")
    return stages[stage_id]


def parse_technical_stage(path: Path) -> TechnicalStage:
    fields = parse_frontmatter(path)
    _require_fields(path, fields, ("stage", "status", "revision"))
    stage_id = fields["stage"]
    revision = _integer(path, "revision", fields["revision"])
    _choice(path, "status", fields["status"], ("REVIEW",))
    _validate_artifact_path(path, stage_id, "technical stage")
    return TechnicalStage(path, stage_id, fields["status"], revision)


def parse_technical_review(path: Path) -> TechnicalReview:
    fields = parse_frontmatter(path)
    _require_fields(path, fields, ("stage", "stage_revision", "status"))
    stage_id = fields["stage"]
    stage_revision = _integer(path, "stage_revision", fields["stage_revision"])
    _choice(path, "status", fields["status"], ("PASS", "REVISE", "MAP_CHANGE_REQUIRED", "BLOCKED"))
    _validate_review_path(path, stage_id, False)
    return TechnicalReview(path, stage_id, stage_revision, fields["status"])


def parse_human_review(path: Path) -> HumanReview:
    fields = parse_frontmatter(path)
    _require_fields(path, fields, ("stage", "status", "revision", "source_revision"))
    stage_id = fields["stage"]
    revision = _integer(path, "revision", fields["revision"])
    source_revision = _integer(path, "source_revision", fields["source_revision"])
    _choice(path, "status", fields["status"], ("REVIEW",))
    _validate_artifact_path(path, stage_id, "human review", human=True)
    return HumanReview(path, stage_id, fields["status"], revision, source_revision)


def parse_human_review_review(path: Path) -> HumanReviewReview:
    fields = parse_frontmatter(path)
    _require_fields(path, fields, ("stage", "stage_revision", "source_revision", "status"))
    stage_id = fields["stage"]
    stage_revision = _integer(path, "stage_revision", fields["stage_revision"])
    source_revision = _integer(path, "source_revision", fields["source_revision"])
    _choice(path, "status", fields["status"], ("PASS", "REVISE", "MAP_CHANGE_REQUIRED", "BLOCKED"))
    _validate_review_path(path, stage_id, True)
    return HumanReviewReview(path, stage_id, stage_revision, source_revision, fields["status"])


def parse_question_state(path: Path) -> QuestionState:
    fields = parse_frontmatter(path)
    _require_fields(path, fields, ("status", "revision"))
    _choice(path, "status", fields["status"], ("pending", "answered"))
    revision = _integer(path, "revision", fields["revision"])
    content = path.read_text(encoding="utf-8")
    heading_answers = re.findall(r"^#{2,4} (?:Answer|Ответ)\s*$\n([^#]+?)(?=\n#{2,4} |\Z)", content, re.MULTILINE)
    inline_answers = re.findall(r"^(?:[-*] )?(?:\*\*(?:Answer|Ответ):\*\*|(?:Answer|Ответ):)\s*(.+)$", content, re.MULTILINE)
    answers = tuple(answer.strip() for answer in heading_answers + inline_answers)
    if not answers:
        _fail(path, "answers", answers, "at least one question answer required")
    return QuestionState(path, fields["status"], revision, answers)


def parse_feedback_state(path: Path) -> FeedbackState:
    fields = parse_frontmatter(path)
    _require_fields(path, fields, ("latest_revision", "mode"))
    latest_revision = _integer(path, "latest_revision", fields["latest_revision"])
    _choice(path, "mode", fields["mode"], ("PLAN_FEEDBACK", "none"))
    content = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^## Feedback (\d+)\s*$", content, re.MULTILINE))
    entries: list[FeedbackEntry] = []
    seen: set[int] = set()
    for index, match in enumerate(matches):
        revision = _integer(path, "Feedback revision", match.group(1))
        if revision != index + 1:
            _fail(path, "Feedback revision", revision, f"expected contiguous revision {index + 1}")
        if revision in seen:
            _fail(path, "Feedback revision", revision, "duplicate feedback entry")
        seen.add(revision)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        values: dict[str, str] = {}
        for line in content[match.end():end].strip().splitlines():
            if not line:
                continue
            if ": " not in line:
                _fail(path, f"Feedback {revision}", line, "expected Field: value")
            key, value = line.split(": ", 1)
            if key in values:
                _fail(path, f"Feedback {revision}.{key}", value, "duplicate field")
            values[key] = value
        _require_fields(path, values, ("Status", "Remarks", "Affected stages", "Questions"), f"Feedback {revision}")
        _choice(path, f"Feedback {revision}.Status", values["Status"], ("pending", "applied"))
        affected = _parse_affected_stages(path, revision, values["Affected stages"])
        entries.append(FeedbackEntry(revision, values["Status"], values["Remarks"], affected, values["Questions"]))
    expected_latest_revision = entries[-1].revision if entries else 0
    if latest_revision != expected_latest_revision:
        _fail(path, "latest_revision", latest_revision, "does not identify latest feedback entry")
    if entries:
        expected_mode = "PLAN_FEEDBACK" if entries[-1].status == "pending" else "none"
        if fields["mode"] != expected_mode:
            _fail(path, "mode", fields["mode"], f"latest feedback status requires {expected_mode!r}")
    elif fields["mode"] != "none":
        _fail(path, "mode", fields["mode"], "empty feedback history requires 'none'")
    return FeedbackState(path, latest_revision, fields["mode"], tuple(entries))


def mutate_plan_frontmatter(path: Path, *, status: str | None = None, current_stage: str | None = None) -> PlanFrontmatter:
    state = parse_plan_frontmatter(path)
    updated = replace(state, status=status if status is not None else state.status, current_stage=current_stage if current_stage is not None else state.current_stage)
    if updated.current_stage != "none":
        _stage_number(path, "current_stage", updated.current_stage)
    _replace_frontmatter(path, {"status": updated.status, "current_stage": updated.current_stage})
    return parse_plan_frontmatter(path)


def mutate_stage_map_entry(path: Path, stage_id: str, **changes: object) -> StageMapEntry:
    entry = parse_stage_map_entry(path, stage_id)
    mutable = set(entry.__dataclass_fields__) - {"stage_id", "title"}
    unknown = sorted(set(changes) - mutable)
    if unknown:
        _fail(path, f"{stage_id}.changes", unknown, "unknown or immutable fields")
    updated = replace(entry, **changes)
    field_values = {
        "Status": updated.status,
        "Revision": str(updated.revision),
        "Depends on": updated.depends_on,
        "Affected area": updated.affected_area,
        "Primary risks": updated.primary_risks,
        "Consumes": updated.consumes,
        "Produces": updated.produces,
        "Details": updated.details,
        "Review": updated.review,
        "Human review": updated.human_review,
        "Human review revision": str(updated.human_review_revision),
        "Human review status": updated.human_review_status,
        "Human review review": updated.human_review_review,
    }
    content = path.read_text(encoding="utf-8")
    heading = f"### {stage_id} — {entry.title}"
    start = content.index(heading)
    end = content.find("\n### ", start + len(heading))
    if end == -1:
        section_end = content.find("\n## ", start + len(heading))
        end = len(content) if section_end == -1 else section_end
    section = content[start:end]
    for field, value in field_values.items():
        source = f"- {field}: {getattr(entry, _stage_attribute(field))}"
        section = _replace_once(path, section, source, f"- {field}: {value}")
    optional_fields = {
        "correction_source_revision": "Correction source revision",
        "human_review_correction_source_revision": "Human review correction source revision",
        "human_review_mismatch_source_revision": "Human review mismatch source revision",
    }
    for attribute, field in optional_fields.items():
        if attribute not in changes:
            continue
        old_value = getattr(entry, attribute)
        new_value = getattr(updated, attribute)
        if new_value is None:
            if old_value is not None:
                section = _replace_once(path, section, f"\n- {field}: {old_value}", "")
        elif old_value is None:
            anchor = f"- Revision: {updated.revision}"
            section = _replace_once(path, section, anchor, f"{anchor}\n- {field}: {new_value}")
        else:
            section = _replace_once(path, section, f"- {field}: {old_value}", f"- {field}: {new_value}")
    content = content[:start] + section + content[end:]
    path.write_text(content, encoding="utf-8")
    return parse_stage_map_entry(path, stage_id)


def mutate_artifact_frontmatter(path: Path, **changes: object) -> None:
    fields = parse_frontmatter(path)
    for key, value in changes.items():
        if key not in fields:
            _fail(path, key, value, "cannot mutate missing field")
    _replace_frontmatter(path, {key: str(value) for key, value in changes.items()})


def write_technical_review(path: Path, stage_id: str, stage_revision: int, status: str, findings: str) -> TechnicalReview:
    _write_review(path, stage_id, stage_revision, status, findings)
    return parse_technical_review(path)


def write_human_review_review(path: Path, stage_id: str, stage_revision: int, source_revision: int, status: str, findings: str) -> HumanReviewReview:
    _validate_review_path(path, stage_id, True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nstage: {stage_id}\nstage_revision: {stage_revision}\nsource_revision: {source_revision}\nstatus: {status}\n---\n\n# Review {stage_id}\n\n## Findings\n- {findings}\n", encoding="utf-8")
    return parse_human_review_review(path)


def write_question_state(path: Path, status: str, revision: int, body: str) -> QuestionState:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nstatus: {status}\nrevision: {revision}\n---\n\n{body.rstrip()}\n", encoding="utf-8")
    return parse_question_state(path)


def write_feedback_state(path: Path, latest_revision: int, mode: str, entries: tuple[FeedbackEntry, ...]) -> FeedbackState:
    if latest_revision != (entries[-1].revision if entries else 0):
        _fail(path, "latest_revision", latest_revision, "does not match entries")
    blocks = ["---", f"latest_revision: {latest_revision}", f"mode: {mode}", "---"]
    for entry in entries:
        affected = "unknown" if entry.affected_stages is None else f"[{', '.join(entry.affected_stages)}]"
        blocks.extend(["", f"## Feedback {entry.revision}", f"Status: {entry.status}", f"Remarks: {entry.remarks}", f"Affected stages: {affected}", f"Questions: {entry.questions}"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return parse_feedback_state(path)


def write_intentionally_malformed_fixture(path: Path, content: str, *, reason: str, parser: Callable[[Path], object], expected_error: str) -> Path:
    if not reason.strip():
        _fail(path, "malformed fixture reason", reason, "explicit reason required")
    if not expected_error:
        _fail(path, "malformed fixture expected_error", expected_error, "expected parser failure required")
    path.write_text(content, encoding="utf-8")
    assert_intentionally_malformed_fixture(path, reason=reason, parser=parser, expected_error=expected_error)
    return path


def assert_intentionally_malformed_fixture(path: Path, *, reason: str, parser: Callable[[Path], object], expected_error: str) -> None:
    if not reason.strip():
        _fail(path, "malformed fixture reason", reason, "explicit reason required")
    try:
        parser(path)
    except AssertionError as error:
        if not re.search(expected_error, str(error)):
            _fail(path, "malformed fixture parser error", str(error), f"expected error matching {expected_error!r}; reason={reason}")
    else:
        _fail(path, "malformed fixture parser", None, f"parser unexpectedly accepted malformed fixture; reason={reason}")


def validate_fixture_state(plan: Path, stage_id: str, artifact_path: Path | None = None, review_path: Path | None = None, *, human: bool = False, expected_plan: PlanFrontmatter | None = None, expected_stage_status: str | None = None, expected_artifact_status: str | None = None, expected_review_status: str | None = None, previous_plan: Path | None = None, invariant_opt_out_reason: str | None = None, expected_invariant_error: str | None = None) -> tuple[StageMapEntry, TechnicalStage | HumanReview | None, TechnicalReview | HumanReviewReview | None]:
    if expected_artifact_status is not None and artifact_path is None:
        _fail(plan, "expected_artifact_status", expected_artifact_status, "artifact path required")
    if expected_review_status is not None and review_path is None:
        _fail(plan, "expected_review_status", expected_review_status, "review path required")
    plan_state = parse_plan_frontmatter(plan)
    if expected_plan is not None and plan_state != expected_plan:
        _fail(plan, "frontmatter", plan_state, f"expected {expected_plan!r}")
    if invariant_opt_out_reason is None and expected_invariant_error is None:
        validate_plan_workflow(plan, previous_plan)
    elif not invariant_opt_out_reason or not invariant_opt_out_reason.strip() or not expected_invariant_error:
        _fail(plan, "invariant opt-out", (invariant_opt_out_reason, expected_invariant_error), "explicit reason and expected invariant error required")
    else:
        try:
            validate_plan_workflow(plan, previous_plan)
        except AssertionError as error:
            if re.search(expected_invariant_error, str(error)) is None:
                _fail(plan, "invariant opt-out error", str(error), f"expected {expected_invariant_error!r}; reason={invariant_opt_out_reason}")
        else:
            _fail(plan, "invariant opt-out", None, f"workflow invariants unexpectedly passed; reason={invariant_opt_out_reason}")
    entry = parse_stage_map_entry(plan, stage_id)
    if expected_stage_status is not None and entry.status != expected_stage_status:
        _fail(plan, f"{stage_id}.Status", entry.status, f"expected {expected_stage_status!r}")
    artifact: TechnicalStage | HumanReview | None = None
    review: TechnicalReview | HumanReviewReview | None = None
    if artifact_path is not None:
        expected = plan.parent / (entry.human_review if human else entry.details)
        if artifact_path != expected:
            _fail(artifact_path, "artifact path", str(artifact_path), f"expected indexed path {expected}")
        if human:
            human_artifact = parse_human_review(artifact_path)
            artifact = human_artifact
            expected_revision = entry.human_review_revision
            if human_artifact.source_revision != entry.revision:
                _fail(artifact_path, "source_revision", human_artifact.source_revision, f"expected indexed technical revision {entry.revision}")
        else:
            artifact = parse_technical_stage(artifact_path)
            expected_revision = entry.revision
        if artifact.stage_id != stage_id or artifact.revision != expected_revision:
            _fail(artifact_path, "artifact identity/revision", (artifact.stage_id, artifact.revision), f"expected {(stage_id, expected_revision)!r}")
        if expected_artifact_status is not None and artifact.status != expected_artifact_status:
            _fail(artifact_path, "artifact status", artifact.status, f"expected {expected_artifact_status!r}")
    if review_path is not None:
        expected = plan.parent / (entry.human_review_review if human else entry.review)
        if review_path != expected:
            _fail(review_path, "review path", str(review_path), f"expected indexed path {expected}")
        if human:
            human_review = parse_human_review_review(review_path)
            review = human_review
            expected_revision = entry.human_review_revision
            if human_review.source_revision != entry.revision:
                _fail(review_path, "source_revision", human_review.source_revision, f"expected indexed technical revision {entry.revision}")
        else:
            review = parse_technical_review(review_path)
            expected_revision = entry.revision
        if review.stage_id != stage_id or review.stage_revision != expected_revision:
            _fail(review_path, "review identity/revision", (review.stage_id, review.stage_revision), f"expected {(stage_id, expected_revision)!r}")
        if expected_review_status is not None and review.status != expected_review_status:
            _fail(review_path, "review status", review.status, f"expected {expected_review_status!r}")
    return entry, artifact, review


def validate_plan_workflow(plan: Path, previous_plan: Path | None = None) -> None:
    state = parse_plan_frontmatter(plan)
    stages = parse_stage_map(plan)
    technical_artifacts = {}
    technical_reviews = {}
    human_artifacts = {}
    human_reviews = {}
    for stage_id, entry in stages.items():
        technical_path = plan.parent / entry.details
        technical_review_path = plan.parent / entry.review
        human_path = plan.parent / entry.human_review
        human_review_path = plan.parent / entry.human_review_review
        if technical_path.is_file():
            technical_artifacts[stage_id] = parse_technical_stage(technical_path)
        if technical_review_path.is_file():
            technical_reviews[stage_id] = parse_technical_review(technical_review_path)
        if human_path.is_file():
            human_artifacts[stage_id] = parse_human_review(human_path)
        if human_review_path.is_file():
            human_reviews[stage_id] = parse_human_review_review(human_review_path)
    previous_stages = parse_stage_map(previous_plan).values() if previous_plan is not None else None
    validate_workflow_invariants(state, stages.values(), technical_artifacts, technical_reviews, human_artifacts, human_reviews, previous_stages)


def _write_review(path: Path, stage_id: str, stage_revision: int, status: str, findings: str) -> None:
    _validate_review_path(path, stage_id, False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nstage: {stage_id}\nstage_revision: {stage_revision}\nstatus: {status}\n---\n\n# Review {stage_id}\n\n## Findings\n- {findings}\n", encoding="utf-8")


def _replace_frontmatter(path: Path, changes: dict[str, str]) -> None:
    fields = parse_frontmatter(path)
    content = path.read_text(encoding="utf-8")
    for key, value in changes.items():
        content = _replace_once(path, content, f"{key}: {fields[key]}", f"{key}: {value}")
    path.write_text(content, encoding="utf-8")


def _replace_once(path: Path, content: str, source: str, replacement: str) -> str:
    count = content.count(source)
    if count != 1:
        _fail(path, "mutation fragment", source, f"expected one match, found {count}")
    return content.replace(source, replacement, 1)


def _stage_attribute(field: str) -> str:
    return {"Status": "status", "Revision": "revision", "Depends on": "depends_on", "Affected area": "affected_area", "Primary risks": "primary_risks", "Consumes": "consumes", "Produces": "produces", "Details": "details", "Review": "review", "Human review": "human_review", "Human review revision": "human_review_revision", "Human review status": "human_review_status", "Human review review": "human_review_review"}[field]


def _require_fields(path: Path, fields: dict[str, str], required: tuple[str, ...], prefix: str = "frontmatter") -> None:
    for field in required:
        if field not in fields:
            _fail(path, f"{prefix}.{field}", None, "required field missing")
        if not fields[field]:
            _fail(path, f"{prefix}.{field}", fields[field], "required value empty")


def _integer(path: Path, field: str, value: str) -> int:
    if not re.fullmatch(r"0|[1-9]\d*", value):
        _fail(path, field, value, "expected non-negative integer")
    return int(value)


def _choice(path: Path, field: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        _fail(path, field, value, f"expected one of {allowed!r}")


def _stage_number(path: Path, field: str, stage_id: str) -> int:
    match = STAGE_ID.fullmatch(stage_id)
    if not match:
        _fail(path, field, stage_id, "expected stage identity SNN")
    return int(match.group(1))


def _validate_artifact_path(path: Path, stage_id: str, field: str, human: bool = False) -> None:
    number = _stage_number(path, "stage", stage_id)
    if path.parent.name != "stages":
        _fail(path, f"{field} parent", path.parent.name, "expected 'stages' parent")
    slug = r"[a-z0-9]+(?:-[a-z0-9]+)*"
    suffix = rf"{slug}\.human-review\.md" if human else rf"{slug}\.md"
    if not re.fullmatch(rf"{number:02d}-{suffix}", path.name):
        _fail(path, field, path.name, f"path does not match {stage_id}")


def _validate_review_path(path: Path, stage_id: str, human: bool) -> None:
    number = _stage_number(path, "stage", stage_id)
    if path.parent.name != "reviews":
        _fail(path, "review parent", path.parent.name, "expected 'reviews' parent")
    expected = f"{number:02d}-human-review.md" if human else f"{number:02d}.md"
    if path.name != expected:
        _fail(path, "review path", path.name, f"expected {expected!r} for {stage_id}")


def _parse_affected_stages(path: Path, revision: int, value: str) -> tuple[str, ...] | None:
    if value == "unknown":
        return None
    match = re.fullmatch(r"\[(.*)\]", value)
    if not match:
        _fail(path, f"Feedback {revision}.Affected stages", value, "expected unknown or [SNN, ...]")
    stages = tuple(item.strip() for item in match.group(1).split(",") if item.strip())
    for stage_id in stages:
        _stage_number(path, f"Feedback {revision}.Affected stages", stage_id)
    if len(stages) != len(set(stages)):
        _fail(path, f"Feedback {revision}.Affected stages", value, "duplicate stage identity")
    return stages


def _fail(path: Path, field: str, value: object, reason: str) -> NoReturn:
    raise AssertionError(f"fixture parse error: path={path}; field={field}; value={value!r}; {reason}")
