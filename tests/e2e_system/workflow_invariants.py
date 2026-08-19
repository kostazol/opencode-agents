from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Iterable, Mapping, NoReturn, Protocol


class PlanState(Protocol):
    @property
    def status(self) -> str: ...

    @property
    def current_stage(self) -> str: ...


class ArtifactIdentity(Protocol):
    @property
    def stage_id(self) -> str: ...


class StageState(ArtifactIdentity, Protocol):
    @property
    def status(self) -> str: ...

    @property
    def revision(self) -> int: ...

    @property
    def depends_on(self) -> str: ...

    @property
    def details(self) -> str: ...

    @property
    def review(self) -> str: ...

    @property
    def human_review(self) -> str: ...

    @property
    def human_review_revision(self) -> int: ...

    @property
    def human_review_status(self) -> str: ...

    @property
    def human_review_review(self) -> str: ...

    @property
    def correction_source_revision(self) -> int | None: ...

    @property
    def human_review_correction_source_revision(self) -> int | None: ...

    @property
    def human_review_mismatch_source_revision(self) -> int | None: ...


class TechnicalArtifactState(ArtifactIdentity, Protocol):
    @property
    def revision(self) -> int: ...


class TechnicalReviewState(ArtifactIdentity, Protocol):
    @property
    def stage_revision(self) -> int: ...

    @property
    def status(self) -> str: ...


class HumanArtifactState(TechnicalArtifactState, Protocol):
    @property
    def source_revision(self) -> int: ...


class HumanReviewState(TechnicalReviewState, Protocol):
    @property
    def source_revision(self) -> int: ...


_STAGE_ID = re.compile(r"^S(\d{2})$")
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_NONE_CURRENT_STATUSES = frozenset({"discovery", "waiting-answers", "waiting-approval", "waiting-plan-approval", "ready", "blocked"})
_REQUIRED_CURRENT_STATUSES = frozenset({"planning", "human-reviewing", "waiting-map-approval"})
_TECHNICAL_ACTIVE_STATUSES = frozenset({"PLANNING", "REVIEW", "BLOCKED", "MAP_CHANGE_REQUIRED"})


def validate_workflow_invariants(plan: PlanState, stages: Iterable[StageState], technical_artifacts: Mapping[str, TechnicalArtifactState] | None = None, technical_reviews: Mapping[str, TechnicalReviewState] | None = None, human_artifacts: Mapping[str, HumanArtifactState] | None = None, human_reviews: Mapping[str, HumanReviewState] | None = None, previous_stages: Iterable[StageState] | None = None) -> None:
    entries = tuple(stages)
    by_id = _unique_stages(entries)
    technical_artifacts = technical_artifacts or {}
    technical_reviews = technical_reviews or {}
    human_artifacts = human_artifacts or {}
    human_reviews = human_reviews or {}
    _validate_current_stage(plan, by_id)
    _validate_active_stage(plan, entries)
    _validate_paths(entries)
    _validate_dependencies(plan, by_id)
    if previous_stages is not None:
        _validate_previous_revisions(by_id, _unique_stages(tuple(previous_stages)))
    _validate_artifact_keys(by_id, technical_artifacts, "technical artifact")
    _validate_artifact_keys(by_id, technical_reviews, "technical review")
    _validate_artifact_keys(by_id, human_artifacts, "human artifact")
    _validate_artifact_keys(by_id, human_reviews, "human review review")
    for stage_id, entry in by_id.items():
        technical = technical_artifacts.get(stage_id)
        review = technical_reviews.get(stage_id)
        human = human_artifacts.get(stage_id)
        human_review = human_reviews.get(stage_id)
        _validate_technical(entry, technical, review)
        _validate_human(entry, human, human_review)
        _validate_revision_provenance(entry)
    _validate_phase_gates(plan, entries, human_artifacts, human_reviews)


def _unique_stages(stages: tuple[StageState, ...]) -> dict[str, StageState]:
    result = {}
    for stage in stages:
        if stage.stage_id in result:
            _fail(f"duplicate stage identity {stage.stage_id}")
        result[stage.stage_id] = stage
    return result


def _validate_current_stage(plan: PlanState, stages: Mapping[str, StageState]) -> None:
    if plan.current_stage == "none":
        if plan.status not in _NONE_CURRENT_STATUSES:
            _fail(f"workflow status {plan.status} requires current_stage")
        return
    if plan.current_stage not in stages:
        _fail(f"current_stage {plan.current_stage} missing from stage map")
    if plan.status not in _REQUIRED_CURRENT_STATUSES | {"discovery", "blocked"}:
        _fail(f"workflow status {plan.status} requires current_stage none")
    current = stages[plan.current_stage]
    if plan.status == "waiting-map-approval" and current.status != "MAP_CHANGE_REQUIRED":
        _fail(f"waiting-map-approval current stage {plan.current_stage} must be MAP_CHANGE_REQUIRED")
    if plan.status == "human-reviewing" and (current.status != "PASS" or current.human_review_status == "PASS"):
        _fail(f"human-reviewing current stage {plan.current_stage} must have technical PASS and unfinished human review")


def _validate_active_stage(plan: PlanState, stages: tuple[StageState, ...]) -> None:
    active = [stage.stage_id for stage in stages if stage.status in _TECHNICAL_ACTIVE_STATUSES]
    if len(active) > 1:
        _fail(f"multiple active technical stages {active}")
    human_active = [stage.stage_id for stage in stages if stage.human_review_status == "REVIEW"]
    if len(human_active) > 1:
        _fail(f"multiple active human-review stages {human_active}")
    for stage_id in active + human_active:
        if plan.current_stage != stage_id:
            _fail(f"active stage {stage_id} does not match current_stage {plan.current_stage}")


def _validate_dependencies(plan: PlanState, stages: Mapping[str, StageState]) -> None:
    for stage in stages.values():
        dependencies = _dependencies(stage.depends_on)
        for dependency in dependencies:
            if dependency not in stages:
                _fail(f"stage {stage.stage_id} dependency {dependency} missing from stage map")
            if int(dependency[1:]) >= int(stage.stage_id[1:]):
                _fail(f"stage {stage.stage_id} dependency {dependency} must be earlier")
        if stage.stage_id == plan.current_stage:
            disallowed = [dependency for dependency in dependencies if stages[dependency].status != "PASS"]
            if disallowed:
                _fail(f"current stage {stage.stage_id} dependencies must be PASS: {disallowed}")


def _dependencies(value: str) -> tuple[str, ...]:
    if value == "none":
        return ()
    dependencies = tuple(item.strip() for item in value.strip("[]").split(",") if item.strip())
    if not dependencies or any(_STAGE_ID.fullmatch(item) is None for item in dependencies):
        _fail(f"invalid dependency list {value!r}")
    if len(dependencies) != len(set(dependencies)):
        _fail(f"duplicate dependency in {value!r}")
    return dependencies


def _validate_paths(stages: tuple[StageState, ...]) -> None:
    seen = {}
    for stage in stages:
        match = _STAGE_ID.fullmatch(stage.stage_id)
        if match is None:
            _fail(f"invalid stage identity {stage.stage_id}")
        number = int(match.group(1))
        details = re.fullmatch(rf"stages/{number:02d}-({_SLUG})\.md", stage.details)
        if details is None:
            _fail(f"stage {stage.stage_id} has non-canonical technical path {stage.details!r}")
        slug = details.group(1)
        expected = (stage.details, f"reviews/{number:02d}.md", f"stages/{number:02d}-{slug}.human-review.md", f"reviews/{number:02d}-human-review.md")
        actual = (stage.details, stage.review, stage.human_review, stage.human_review_review)
        for path in actual:
            canonical = PurePosixPath(path)
            if str(canonical) != path or path in seen:
                _fail(f"duplicate or non-canonical indexed path {path!r}")
            seen[path] = stage.stage_id
        if actual != expected:
            _fail(f"stage {stage.stage_id} has non-canonical indexed paths {actual!r}; expected {expected!r}")


def _validate_previous_revisions(stages: Mapping[str, StageState], previous: Mapping[str, StageState]) -> None:
    for stage_id, old in previous.items():
        current = stages.get(stage_id)
        if current is None:
            continue
        if current.revision < old.revision:
            _fail(f"stage {stage_id} technical revision decreased from {old.revision} to {current.revision}")
        if current.human_review_revision < old.human_review_revision:
            _fail(f"stage {stage_id} human-review revision decreased from {old.human_review_revision} to {current.human_review_revision}")


def _validate_revision_provenance(entry: StageState) -> None:
    if entry.correction_source_revision is not None and entry.revision != entry.correction_source_revision + 1:
        _fail(f"stage {entry.stage_id} correction source revision {entry.correction_source_revision} must precede technical revision {entry.revision}")
    if entry.human_review_correction_source_revision is not None and entry.human_review_revision != entry.human_review_correction_source_revision + 1:
        _fail(f"stage {entry.stage_id} human review correction source revision {entry.human_review_correction_source_revision} must precede human revision {entry.human_review_revision}")
    if entry.human_review_mismatch_source_revision is not None and entry.human_review_revision != entry.human_review_mismatch_source_revision + 1:
        _fail(f"stage {entry.stage_id} human review mismatch source revision {entry.human_review_mismatch_source_revision} must precede human revision {entry.human_review_revision}")


def _validate_artifact_keys(stages: Mapping[str, StageState], artifacts: Mapping[str, ArtifactIdentity], family: str) -> None:
    for key, artifact in artifacts.items():
        if key not in stages:
            _fail(f"{family} key {key} missing from stage map")
        if artifact.stage_id != key:
            _fail(f"{family} key {key} contains stage {artifact.stage_id}")


def _validate_technical(entry: StageState, artifact: TechnicalArtifactState | None, review: TechnicalReviewState | None) -> None:
    if artifact is not None and artifact.revision > entry.revision:
        _fail(f"stage {entry.stage_id} indexed technical revision {entry.revision} trails artifact revision {artifact.revision}")
    if review is not None and review.stage_revision > entry.revision:
        _fail(f"stage {entry.stage_id} indexed technical revision {entry.revision} trails review revision {review.stage_revision}")
    if review is not None and review.stage_revision == entry.revision and artifact is None:
        _fail(f"stage {entry.stage_id} technical review revision {review.stage_revision} requires matching stage artifact")
    if artifact is not None and review is not None and review.stage_revision == entry.revision and artifact.revision != review.stage_revision:
        _fail(f"stage {entry.stage_id} technical review revision {review.stage_revision} does not match stage artifact revision {artifact.revision}")
    if entry.status == "REVIEW" and (artifact is None or artifact.revision != entry.revision):
        _fail(f"stage {entry.stage_id} REVIEW status requires technical artifact revision {entry.revision}")
    if entry.status == "PASS":
        if artifact is None or artifact.revision != entry.revision:
            _fail(f"stage {entry.stage_id} PASS status requires technical artifact revision {entry.revision}")
        if review is None or review.stage_revision != entry.revision or review.status != "PASS":
            _fail(f"stage {entry.stage_id} PASS status requires PASS review revision {entry.revision}")


def _validate_human(entry: StageState, artifact: HumanArtifactState | None, review: HumanReviewState | None) -> None:
    if artifact is not None and artifact.revision > entry.human_review_revision:
        _fail(f"stage {entry.stage_id} indexed human-review revision {entry.human_review_revision} trails artifact revision {artifact.revision}")
    if review is not None and review.stage_revision > entry.human_review_revision:
        _fail(f"stage {entry.stage_id} indexed human-review revision {entry.human_review_revision} trails review revision {review.stage_revision}")
    if artifact is not None and artifact.revision == entry.human_review_revision and artifact.source_revision != entry.revision:
        _fail(f"stage {entry.stage_id} human-review source revision {artifact.source_revision} does not match technical revision {entry.revision}")
    if review is not None and review.stage_revision == entry.human_review_revision:
        if artifact is None or artifact.revision != review.stage_revision:
            _fail(f"stage {entry.stage_id} human review review revision {review.stage_revision} does not match human artifact")
        assert artifact is not None
        if review.source_revision != entry.revision or review.source_revision != artifact.source_revision:
            _fail(f"stage {entry.stage_id} human review review source revision {review.source_revision} does not match technical and human revisions")
    if entry.human_review_status == "REVIEW" and (artifact is None or artifact.revision != entry.human_review_revision or artifact.source_revision != entry.revision):
        _fail(f"stage {entry.stage_id} human REVIEW status requires matching human artifact")
    if entry.human_review_status == "PASS":
        if artifact is None or artifact.revision != entry.human_review_revision or artifact.source_revision != entry.revision:
            _fail(f"stage {entry.stage_id} human PASS status requires matching human artifact")
        if review is None or review.stage_revision != entry.human_review_revision or review.source_revision != entry.revision or review.status != "PASS":
            _fail(f"stage {entry.stage_id} human PASS status requires matching PASS review")


def _validate_phase_gates(plan: PlanState, stages: tuple[StageState, ...], human_artifacts: Mapping[str, HumanArtifactState], human_reviews: Mapping[str, HumanReviewState]) -> None:
    for stage in stages:
        artifact = human_artifacts.get(stage.stage_id)
        review = human_reviews.get(stage.stage_id)
        current_artifact = artifact is not None and artifact.revision == stage.human_review_revision
        current_review = review is not None and review.stage_revision == stage.human_review_revision
        if (stage.human_review_status != "PENDING" or current_artifact or current_review) and stage.status != "PASS":
            _fail(f"stage {stage.stage_id} human review activity requires technical PASS")
    if plan.status == "human-reviewing" and any(stage.status != "PASS" for stage in stages):
        _fail("human-reviewing requires every technical stage PASS")
    if plan.status in ("waiting-plan-approval", "ready"):
        unfinished = [stage.stage_id for stage in stages if stage.status != "PASS" or stage.human_review_status != "PASS"]
        if unfinished:
            _fail(f"workflow status {plan.status} requires every technical and human review PASS: {unfinished}")


def _fail(message: str) -> NoReturn:
    raise AssertionError(f"workflow invariant error: {message}")
