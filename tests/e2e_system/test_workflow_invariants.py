#!/usr/bin/env python3

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from typing import Any

from fixture_validation import HumanReview, HumanReviewReview, PlanFrontmatter, StageMapEntry, TechnicalReview, TechnicalStage, parse_stage_map, validate_plan_workflow
from workflow_invariants import validate_workflow_invariants


class WorkflowInvariantTests(unittest.TestCase):
    def test_valid_reset_state_accepts_stale_known_artifacts(self):
        stage = self._stage("S01", revision=2, human_revision=2)
        technical = TechnicalStage(Path("stages/01-value.md"), "S01", "REVIEW", 1)
        review = TechnicalReview(Path("reviews/01.md"), "S01", 1, "PASS")
        human = HumanReview(Path("stages/01-value.human-review.md"), "S01", "REVIEW", 1, 1)
        human_review = HumanReviewReview(Path("reviews/01-human-review.md"), "S01", 1, 1, "PASS")
        validate_workflow_invariants(PlanFrontmatter("planning", "S01"), (stage,), {"S01": technical}, {"S01": review}, {"S01": human}, {"S01": human_review})

    def test_rejects_multiple_active_technical_stages(self):
        stages = (replace(self._stage("S01"), status="PLANNING"), replace(self._stage("S02"), status="REVIEW"))
        self._assert_invalid("multiple active technical stages", PlanFrontmatter("planning", "S01"), stages)

    def test_rejects_multiple_active_human_stages(self):
        stages = (replace(self._stage("S01"), human_review_status="REVIEW"), replace(self._stage("S02"), human_review_status="REVIEW"))
        self._assert_invalid("multiple active human-review stages", PlanFrontmatter("planning", "S01"), stages)

    def test_rejects_missing_current_stage_and_none_in_active_state(self):
        with self.subTest(case="missing"):
            self._assert_invalid("current_stage S02 missing", PlanFrontmatter("planning", "S02"), (self._stage("S01"),))
        with self.subTest(case="none"):
            self._assert_invalid("planning requires current_stage", PlanFrontmatter("planning", "none"), (self._stage("S01"),))

    def test_rejects_revision_decrease_against_previous_map(self):
        current = self._stage("S01", revision=2, human_revision=2)
        with self.subTest(revision="technical"):
            self._assert_invalid("technical revision decreased", PlanFrontmatter("planning", "S01"), (current,), previous_stages=(replace(current, revision=3),))
        with self.subTest(revision="human"):
            self._assert_invalid("human-review revision decreased", PlanFrontmatter("planning", "S01"), (current,), previous_stages=(replace(current, human_review_revision=3),))

    def test_rejects_invalid_revision_provenance(self):
        cases = (
            ("correction_source_revision", 2, "correction source revision"),
            ("human_review_correction_source_revision", 1, "human review correction source revision"),
            ("human_review_mismatch_source_revision", 1, "human review mismatch source revision"),
        )
        for field, value, diagnostic in cases:
            with self.subTest(field=field):
                stage = replace(self._stage("S01", revision=2, human_revision=3), **{field: value})
                self._assert_invalid(diagnostic, PlanFrontmatter("planning", "S01"), (stage,))

    def test_rejects_index_revision_behind_known_artifacts(self):
        stage = self._stage("S01", revision=1, human_revision=1)
        with self.subTest(artifact="technical"):
            technical = TechnicalStage(Path("stages/01-value.md"), "S01", "REVIEW", 2)
            self._assert_invalid("trails artifact revision 2", PlanFrontmatter("planning", "S01"), (stage,), technical_artifacts={"S01": technical})
        with self.subTest(artifact="human"):
            human = HumanReview(Path("stages/01-value.human-review.md"), "S01", "REVIEW", 2, 1)
            self._assert_invalid("trails artifact revision 2", PlanFrontmatter("planning", "S01"), (stage,), human_artifacts={"S01": human})

    def test_rejects_missing_and_unpassed_current_dependencies(self):
        current = replace(self._stage("S02"), depends_on="S01")
        with self.subTest(case="missing"):
            self._assert_invalid("dependency S01 missing", PlanFrontmatter("planning", "S02"), (current,))
        with self.subTest(case="unpassed"):
            self._assert_invalid("dependencies must be PASS", PlanFrontmatter("planning", "S02"), (self._stage("S01"), current))

    def test_rejects_every_noncanonical_indexed_path_family(self):
        changes = {"details": "stages/01-Value.md", "review": "reviews/02.md", "human_review": "stages/01-other.human-review.md", "human_review_review": "reviews/02-human-review.md"}
        for field, value in changes.items():
            with self.subTest(field=field):
                self._assert_invalid("non-canonical", PlanFrontmatter("planning", "S01"), (replace(self._stage("S01"), **{field: value}),))

    def test_rejects_status_without_matching_artifacts(self):
        with self.subTest(status="technical REVIEW"):
            self._assert_invalid("REVIEW status requires technical artifact", PlanFrontmatter("planning", "S01"), (replace(self._stage("S01"), status="REVIEW"),))
        with self.subTest(status="technical PASS"):
            self._assert_invalid("PASS status requires technical artifact", PlanFrontmatter("planning", "S01"), (replace(self._stage("S01"), status="PASS"),))
        with self.subTest(status="human PASS"):
            self._assert_invalid("human PASS status requires matching human artifact", PlanFrontmatter("planning", "S01"), (replace(self._stage("S01"), human_review_status="PASS"),))

    def test_rejects_technical_review_revision_mismatch(self):
        entry = replace(self._stage("S01"), status="REVIEW")
        technical = TechnicalStage(Path("stages/01-value.md"), "S01", "REVIEW", 0)
        review = TechnicalReview(Path("reviews/01.md"), "S01", 1, "REVISE")
        self._assert_invalid("does not match stage artifact revision", PlanFrontmatter("planning", "S01"), (entry,), technical_artifacts={"S01": technical}, technical_reviews={"S01": review})

    def test_rejects_current_technical_review_without_stage_artifact(self):
        review = TechnicalReview(Path("reviews/01.md"), "S01", 1, "REVISE")
        self._assert_invalid("requires matching stage artifact", PlanFrontmatter("planning", "S01"), (self._stage("S01"),), technical_reviews={"S01": review})

    def test_rejects_human_revision_and_source_mismatch(self):
        entry = self._stage("S01", revision=2, human_revision=1)
        human = HumanReview(Path("stages/01-value.human-review.md"), "S01", "REVIEW", 1, 1)
        self._assert_invalid("source revision 1 does not match technical revision 2", PlanFrontmatter("planning", "S01"), (entry,), human_artifacts={"S01": human})

    def test_rejects_human_review_review_revision_and_source_mismatch(self):
        entry = self._stage("S01", revision=2, human_revision=1)
        with self.subTest(field="revision"):
            human = HumanReview(Path("stages/01-value.human-review.md"), "S01", "REVIEW", 0, 1)
            review = HumanReviewReview(Path("reviews/01-human-review.md"), "S01", 1, 2, "PASS")
            self._assert_invalid("does not match human artifact", PlanFrontmatter("planning", "S01"), (entry,), human_artifacts={"S01": human}, human_reviews={"S01": review})
        with self.subTest(field="source"):
            human = HumanReview(Path("stages/01-value.human-review.md"), "S01", "REVIEW", 1, 2)
            review = HumanReviewReview(Path("reviews/01-human-review.md"), "S01", 1, 1, "PASS")
            self._assert_invalid("source revision 1 does not match", PlanFrontmatter("planning", "S01"), (entry,), human_artifacts={"S01": human}, human_reviews={"S01": review})

    def test_rejects_human_activity_before_technical_pass(self):
        entry = replace(self._stage("S01", human_revision=1), status="REVIEW", human_review_status="REVIEW")
        technical = TechnicalStage(Path("stages/01-value.md"), "S01", "REVIEW", 1)
        human = HumanReview(Path("stages/01-value.human-review.md"), "S01", "REVIEW", 1, 1)
        self._assert_invalid("human review activity requires technical PASS", PlanFrontmatter("planning", "S01"), (entry,), technical_artifacts={"S01": technical}, human_artifacts={"S01": human})

    def test_rejects_human_review_phase_before_all_technical_pass(self):
        first = replace(self._stage("S01"), status="PASS")
        second = self._stage("S02")
        technical = TechnicalStage(Path("stages/01-value.md"), "S01", "REVIEW", 1)
        review = TechnicalReview(Path("reviews/01.md"), "S01", 1, "PASS")
        self._assert_invalid("human-reviewing requires every technical stage PASS", PlanFrontmatter("human-reviewing", "S01"), (first, second), technical_artifacts={"S01": technical}, technical_reviews={"S01": review})

    def test_rejects_approval_and_ready_before_all_human_reviews_pass(self):
        entry = replace(self._stage("S01"), status="PASS")
        technical = TechnicalStage(Path("stages/01-value.md"), "S01", "REVIEW", 1)
        review = TechnicalReview(Path("reviews/01.md"), "S01", 1, "PASS")
        for status in ("waiting-plan-approval", "ready"):
            with self.subTest(status=status):
                self._assert_invalid("requires every technical and human review PASS", PlanFrontmatter(status, "none"), (entry,), technical_artifacts={"S01": technical}, technical_reviews={"S01": review})

    def test_rejects_duplicate_stage_ids_and_indexed_paths(self):
        with self.subTest(case="identity"):
            self._assert_invalid("duplicate stage identity S01", PlanFrontmatter("planning", "S01"), (self._stage("S01"), self._stage("S01")))
        with self.subTest(case="path"):
            duplicate = replace(self._stage("S02"), details="stages/01-value.md")
            self._assert_invalid("non-canonical technical path", PlanFrontmatter("planning", "S01"), (self._stage("S01"), duplicate))

    def test_direct_parser_rejects_intentionally_duplicate_stage_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = Path(temporary) / "plan.md"
            section = "### S01 — Test\n- Status: PROPOSED\n- Revision: 0\n- Depends on: none\n- Affected area: value\n- Primary risks: contract\n- Consumes: none\n- Produces: value\n- Details: stages/01-value.md\n- Review: reviews/01.md\n- Human review: stages/01-value.human-review.md\n- Human review revision: 0\n- Human review status: PENDING\n- Human review review: reviews/01-human-review.md\n"
            plan.write_text(f"---\nstatus: planning\ncurrent_stage: S01\n---\n\n## Stage map\n\n{section}\n{section}", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "duplicate stage map entry"):
                parse_stage_map(plan)

    def test_fixture_precondition_runs_workflow_invariants(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = Path(temporary) / "plan.md"
            plan.write_text("---\nstatus: planning\ncurrent_stage: none\n---\n\n## Stage map\n\n### S01 — Test\n- Status: PROPOSED\n- Revision: 0\n- Depends on: none\n- Affected area: value\n- Primary risks: contract\n- Consumes: none\n- Produces: value\n- Details: stages/01-value.md\n- Review: reviews/01.md\n- Human review: stages/01-value.human-review.md\n- Human review revision: 0\n- Human review status: PENDING\n- Human review review: reviews/01-human-review.md\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "planning requires current_stage"):
                validate_plan_workflow(plan)

    def test_fixture_precondition_checks_previous_plan_revisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous = root / "previous-plan.md"
            current = root / "current-plan.md"
            template = "---\nstatus: planning\ncurrent_stage: S01\n---\n\n## Stage map\n\n### S01 — Test\n- Status: PROPOSED\n- Revision: {revision}\n- Depends on: none\n- Affected area: value\n- Primary risks: contract\n- Consumes: none\n- Produces: value\n- Details: stages/01-value.md\n- Review: reviews/01.md\n- Human review: stages/01-value.human-review.md\n- Human review revision: {revision}\n- Human review status: PENDING\n- Human review review: reviews/01-human-review.md\n"
            previous.write_text(template.format(revision=2), encoding="utf-8")
            current.write_text(template.format(revision=1), encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "technical revision decreased"):
                validate_plan_workflow(current, previous)

    def _stage(self, stage_id: str, revision: int = 1, human_revision: int = 0) -> StageMapEntry:
        number = int(stage_id[1:])
        slug = "value" if number == 1 else f"value-{number}"
        return StageMapEntry(stage_id, "Test", "PROPOSED", revision, "none", "value", "contract", "none", "value", f"stages/{number:02d}-{slug}.md", f"reviews/{number:02d}.md", f"stages/{number:02d}-{slug}.human-review.md", human_revision, "PENDING", f"reviews/{number:02d}-human-review.md")

    def _assert_invalid(self, message: str, plan: PlanFrontmatter, stages: tuple[StageMapEntry, ...], **kwargs: Any) -> None:
        with self.assertRaisesRegex(AssertionError, message):
            validate_workflow_invariants(plan, stages, **kwargs)


if __name__ == "__main__":
    unittest.main()
