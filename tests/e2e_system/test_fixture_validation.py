#!/usr/bin/env python3

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fixture_validation import FeedbackEntry, HumanReview, HumanReviewReview, PlanFrontmatter, QuestionState, TechnicalReview, TechnicalStage, mutate_artifact_frontmatter, mutate_plan_frontmatter, mutate_stage_map_entry, parse_feedback_state, parse_human_review, parse_human_review_review, parse_plan_frontmatter, parse_question_state, parse_stage_map, parse_stage_map_entry, parse_technical_review, parse_technical_stage, replace_required, validate_fixture_state, write_feedback_state, write_human_review_review, write_intentionally_malformed_fixture, write_question_state, write_technical_review


class FixtureValidationTests(unittest.TestCase):
    def test_replace_required_writes_expected_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.md"
            path.write_text("revision: 1\n", encoding="utf-8")
            replace_required(path, "revision: 1", "revision: 2")
            self.assertEqual(path.read_text(encoding="utf-8"), "revision: 2\n")

    def test_replace_required_rejects_missing_fragment_before_live_call(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.md"
            path.write_text("revision: 1\n", encoding="utf-8")
            live_call = Mock()
            with self.assertRaisesRegex(AssertionError, "expected 1, found 0"):
                replace_required(path, "revision: 0", "revision: 2")
                live_call()
            live_call.assert_not_called()

    def test_parsers_return_typed_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan, stage, review, human, human_review = self._write_state(root)
            self.assertEqual(parse_plan_frontmatter(plan), PlanFrontmatter("planning", "S01"))
            self.assertEqual(parse_stage_map_entry(plan, "S01").revision, 1)
            self.assertEqual(parse_technical_stage(stage), TechnicalStage(stage, "S01", "REVIEW", 1))
            self.assertEqual(parse_technical_review(review), TechnicalReview(review, "S01", 1, "PASS"))
            self.assertEqual(parse_human_review(human), HumanReview(human, "S01", "REVIEW", 1, 1))
            self.assertEqual(parse_human_review_review(human_review), HumanReviewReview(human_review, "S01", 1, 1, "PASS"))

    def test_canonical_mutations_preserve_consistent_typed_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, stage, _, _, _ = self._write_state(Path(temporary))
            self.assertEqual(mutate_plan_frontmatter(plan, status="blocked"), PlanFrontmatter("blocked", "S01"))
            entry = mutate_stage_map_entry(plan, "S01", status="BLOCKED", revision=3, human_review_revision=2)
            self.assertEqual((entry.status, entry.revision, entry.human_review_revision), ("BLOCKED", 3, 2))
            mutate_artifact_frontmatter(stage, revision=3)
            self.assertEqual(parse_technical_stage(stage).revision, 3)

    def test_review_builders_require_canonical_identity_and_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "reviews"
            technical = write_technical_review(root / "01.md", "S01", 2, "REVISE", "Исправить контракт.")
            human = write_human_review_review(root / "01-human-review.md", "S01", 3, 2, "PASS", "Нет.")
            self.assertEqual((technical.stage_revision, technical.status), (2, "REVISE"))
            self.assertEqual((human.stage_revision, human.source_revision), (3, 2))
            with self.assertRaisesRegex(AssertionError, r"field=review path; value='02.md'"):
                write_technical_review(root / "02.md", "S01", 1, "PASS", "Нет.")

    def test_fixture_validation_rejects_cross_artifact_revision_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, stage, review, human, human_review = self._write_state(Path(temporary))
            entry, artifact, parsed_review = validate_fixture_state(plan, "S01", stage, review)
            self.assertIsNotNone(artifact)
            self.assertIsNotNone(parsed_review)
            assert artifact is not None and parsed_review is not None
            self.assertEqual((entry.revision, artifact.revision, parsed_review.stage_revision), (1, 1, 1))
            validate_fixture_state(plan, "S01", human, human_review, human=True)
            mutate_artifact_frontmatter(stage, revision=2)
            with self.assertRaisesRegex(AssertionError, r"field=artifact identity/revision; value=\('S01', 2\)"):
                validate_fixture_state(plan, "S01", stage, review, invariant_opt_out_reason="Exercise lower-level artifact identity diagnostic after deliberate revision corruption.", expected_invariant_error="trails artifact revision 2")

    def test_fixture_validation_rejects_wrong_expected_status_before_live_call(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, stage, review, _, _ = self._write_state(Path(temporary))
            live_call = Mock()
            with self.assertRaisesRegex(AssertionError, r"field=S01.Status; value='PASS'; expected 'REVIEW'"):
                validate_fixture_state(plan, "S01", stage, review, expected_plan=PlanFrontmatter("planning", "S01"), expected_stage_status="REVIEW", expected_artifact_status="REVIEW", expected_review_status="PASS")
                live_call()
            live_call.assert_not_called()

    def test_invariant_opt_out_requires_reason_and_expected_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, stage, review, _, _ = self._write_state(Path(temporary))
            with self.assertRaisesRegex(AssertionError, "explicit reason and expected invariant error required"):
                validate_fixture_state(plan, "S01", stage, review, invariant_opt_out_reason="test-only malformed state")

    def test_question_and_feedback_builders_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            question = write_question_state(root / "questions.md", "pending", 1, "# Вопросы\n\n## Q1 — Формат\n\n### Ответ\npending")
            self.assertEqual(question, QuestionState(root / "questions.md", "pending", 1, ("pending",)))
            question.path.write_text("---\nstatus: pending\nrevision: 1\n---\n\n## Вопрос 1\n\n- **Ответ:** pending\n", encoding="utf-8")
            self.assertEqual(parse_question_state(question.path).answers, ("pending",))
            expected = (FeedbackEntry(1, "pending", "Нужно значение 2.", ("S01",), "none"),)
            feedback = write_feedback_state(root / "feedback.md", 1, "PLAN_FEEDBACK", expected)
            self.assertEqual(feedback.entries, expected)
            self.assertEqual(parse_feedback_state(root / "feedback.md"), feedback)
            feedback.path.write_text(feedback.path.read_text(encoding="utf-8").replace("latest_revision: 1", "latest_revision: 0"), encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "does not identify latest feedback entry"):
                parse_feedback_state(feedback.path)

    def test_frontmatter_rejects_duplicate_and_missing_required_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.md"
            path.write_text("---\nstatus: planning\nstatus: ready\ncurrent_stage: S01\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, r"path=.*plan.md; field=status; value='ready'; duplicate field"):
                parse_plan_frontmatter(path)
            path.write_text("---\nstatus: planning\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, r"field=frontmatter.current_stage; value=None; required field missing"):
                parse_plan_frontmatter(path)

    def test_stage_map_only_reads_stage_map_section(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, _, _, _, _ = self._write_state(Path(temporary))
            with plan.open("a", encoding="utf-8") as output:
                output.write("\n## Pending map change\n\n### S02 — Outside\n- Status: PASS\n")
            self.assertEqual(set(parse_stage_map(plan)), {"S01"})

    def test_stage_map_rejects_duplicate_missing_and_non_integer_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, _, _, _, _ = self._write_state(Path(temporary))
            replace_required(plan, "- Status: PASS", "- Status: PASS\n- Status: PASS")
            with self.assertRaisesRegex(AssertionError, r"field=S01.Status; value='PASS'; duplicate field"):
                parse_stage_map(plan)
            plan, _, _, _, _ = self._write_state(Path(temporary))
            replace_required(plan, "- Review: reviews/01.md\n", "")
            with self.assertRaisesRegex(AssertionError, r"field=S01.Review; value=None; required field missing"):
                parse_stage_map(plan)
            plan, _, _, _, _ = self._write_state(Path(temporary))
            replace_required(plan, "- Revision: 1", "- Revision: first")
            with self.assertRaisesRegex(AssertionError, r"field=S01.Revision; value='first'; expected non-negative integer"):
                parse_stage_map(plan)

    def test_stage_map_rejects_inconsistent_indexed_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, _, _, _, _ = self._write_state(Path(temporary))
            replace_required(plan, "- Human review review: reviews/01-human-review.md", "- Human review review: reviews/02-human-review.md")
            with self.assertRaisesRegex(AssertionError, r"field=S01.Human review review; value='reviews/02-human-review.md'"):
                parse_stage_map(plan)

    def test_stage_map_rejects_unsafe_slug_segments(self):
        with tempfile.TemporaryDirectory() as temporary:
            for unsafe in ("stages/01-../value.md", "stages/01-nested/value.md", "stages/01-value.contract.md"):
                with self.subTest(unsafe=unsafe):
                    plan, _, _, _, _ = self._write_state(Path(temporary))
                    replace_required(plan, "stages/01-value-contract.md", unsafe, expected_count=1)
                    with self.assertRaisesRegex(AssertionError, r"field=S01.Details; .*non-canonical indexed path"):
                        parse_stage_map(plan)

    def test_artifact_parsers_require_exact_parent_family(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, stage, review, human, human_review = self._write_state(Path(temporary))
            cases = ((stage, parse_technical_stage, "technical stage parent"), (human, parse_human_review, "human review parent"), (review, parse_technical_review, "review parent"), (human_review, parse_human_review_review, "review parent"))
            for source, parser, field in cases:
                with self.subTest(path=source):
                    wrong_parent = source.parent.parent / source.name
                    wrong_parent.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
                    with self.assertRaisesRegex(AssertionError, rf"field={field};"):
                        parser(wrong_parent)

    def test_artifact_parsers_reject_unsafe_slug(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, stage, _, human, _ = self._write_state(root)
            unsafe_stage = stage.with_name("01-value.contract.md")
            unsafe_stage.write_text(stage.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, r"field=technical stage; value='01-value.contract.md'"):
                parse_technical_stage(unsafe_stage)
            unsafe_human = human.with_name("01-..human-review.md")
            unsafe_human.write_text(human.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, r"field=human review; value='01-..human-review.md'"):
                parse_human_review(unsafe_human)

    def test_intentionally_malformed_writer_requires_reason_and_parser_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.md"
            malformed = "---\nstatus: planning\n---\n"
            write_intentionally_malformed_fixture(path, malformed, reason="Legacy plan intentionally omits current_stage.", parser=parse_plan_frontmatter, expected_error=r"field=frontmatter.current_stage")
            with self.assertRaisesRegex(AssertionError, "explicit reason required"):
                write_intentionally_malformed_fixture(path, malformed, reason="", parser=parse_plan_frontmatter, expected_error=r"current_stage")
            with self.assertRaisesRegex(AssertionError, "parser unexpectedly accepted malformed fixture"):
                write_intentionally_malformed_fixture(path, "---\nstatus: planning\ncurrent_stage: S01\n---\n", reason="Must prove malformed state.", parser=parse_plan_frontmatter, expected_error=r"current_stage")

    def test_artifact_parsers_reject_stage_identity_and_revision_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, stage, review, human, _ = self._write_state(Path(temporary))
            mutate_artifact_frontmatter(stage, stage="S02")
            with self.assertRaisesRegex(AssertionError, r"field=technical stage; value='01-value-contract.md'"):
                parse_technical_stage(stage)
            mutate_artifact_frontmatter(review, stage_revision="one")
            with self.assertRaisesRegex(AssertionError, r"field=stage_revision; value='one'"):
                parse_technical_review(review)
            mutate_artifact_frontmatter(human, source_revision="")
            with self.assertRaisesRegex(AssertionError, r"field=frontmatter.source_revision; value=''; required value empty"):
                parse_human_review(human)

    def test_question_and_feedback_reject_inconsistent_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            question = root / "questions.md"
            question.write_text("---\nstatus: pending\nrevision: one\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, r"field=revision; value='one'"):
                parse_question_state(question)
            feedback = root / "feedback.md"
            feedback.write_text("---\nlatest_revision: 2\nmode: PLAN_FEEDBACK\n---\n\n## Feedback 1\nStatus: pending\nRemarks: x\nAffected stages: [S01]\nQuestions: none\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, r"field=latest_revision; value=2"):
                parse_feedback_state(feedback)
            feedback.write_text("---\nlatest_revision: 2\nmode: none\n---\n\n## Feedback 2\nStatus: applied\nRemarks: x\nAffected stages: [S01]\nQuestions: none\n\n## Feedback 1\nStatus: applied\nRemarks: y\nAffected stages: [S01]\nQuestions: none\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, r"expected contiguous revision 1"):
                parse_feedback_state(feedback)
            feedback.write_text("---\nlatest_revision: 0\nmode: PLAN_FEEDBACK\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, r"empty feedback history requires 'none'"):
                parse_feedback_state(feedback)

    def _write_state(self, root: Path) -> tuple[Path, Path, Path, Path, Path]:
        stages = root / "stages"
        reviews = root / "reviews"
        stages.mkdir(exist_ok=True)
        reviews.mkdir(exist_ok=True)
        plan = root / "plan.md"
        stage = stages / "01-value-contract.md"
        review = reviews / "01.md"
        human = stages / "01-value-contract.human-review.md"
        human_review = reviews / "01-human-review.md"
        plan.write_text("---\nstatus: planning\ncurrent_stage: S01\n---\n\n## Stage map\n\n### S01 — Test\n- Status: PASS\n- Revision: 1\n- Depends on: none\n- Affected area: value\n- Primary risks: contract\n- Consumes: none\n- Produces: value\n- Details: stages/01-value-contract.md\n- Review: reviews/01.md\n- Human review: stages/01-value-contract.human-review.md\n- Human review revision: 1\n- Human review status: PASS\n- Human review review: reviews/01-human-review.md\n", encoding="utf-8")
        stage.write_text("---\nstage: S01\nstatus: REVIEW\nrevision: 1\n---\n", encoding="utf-8")
        review.write_text("---\nstage: S01\nstage_revision: 1\nstatus: PASS\n---\n", encoding="utf-8")
        human.write_text("---\nstage: S01\nstatus: REVIEW\nrevision: 1\nsource_revision: 1\n---\n", encoding="utf-8")
        human_review.write_text("---\nstage: S01\nstage_revision: 1\nsource_revision: 1\nstatus: PASS\n---\n", encoding="utf-8")
        return plan, stage, review, human, human_review


if __name__ == "__main__":
    unittest.main()
