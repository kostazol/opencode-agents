#!/usr/bin/env python3

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fixture_validation import assert_fixture_state, replace_required


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
            self.assertEqual(path.read_text(encoding="utf-8"), "revision: 1\n")

    def test_replace_required_rejects_unexpected_match_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.md"
            path.write_text("status: PENDING\nstatus: PENDING\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "expected 1, found 2"):
                replace_required(path, "status: PENDING", "status: PASS")

    def test_assert_fixture_state_rejects_wrong_resulting_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, stage, review = self._write_state(Path(temporary))
            with self.assertRaisesRegex(AssertionError, "fixture state mismatch"):
                assert_fixture_state(plan, "planning", "S01", "S01", {"Status": "REVIEW", "Revision": "3"}, stage, {"revision": "3"}, review, {"stage_revision": "3", "status": "REVISE"})

    def test_assert_fixture_state_rejects_wrong_resulting_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, stage, review = self._write_state(Path(temporary))
            with self.assertRaisesRegex(AssertionError, "fixture state mismatch"):
                assert_fixture_state(plan, "planning", "S01", "S01", {"Status": "PASS", "Revision": "1"}, stage, {"revision": "1"}, review, {"stage_revision": "1", "status": "REVISE"})

    def test_pending_map_change_fields_cannot_satisfy_stage_expectation(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, stage, review = self._write_state(Path(temporary))
            with plan.open("a", encoding="utf-8") as output:
                output.write("\n## Pending map change\n\n- Evidence: outside stage map\n")
            with self.assertRaisesRegex(AssertionError, "fixture state mismatch"):
                assert_fixture_state(plan, "planning", "S01", "S01", {"Status": "REVIEW", "Revision": "1", "Evidence": "outside stage map"}, stage, {"revision": "1"}, review, {"stage_revision": "1", "status": "REVISE"})

    def test_assert_fixture_state_rejects_technical_artifact_for_other_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, stage, review = self._write_state(Path(temporary))
            stage.write_text("---\nstage: S02\nstatus: REVIEW\nrevision: 1\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "fixture state mismatch"):
                assert_fixture_state(plan, "planning", "S01", "S01", {"Status": "REVIEW", "Revision": "1"}, stage, {"revision": "1"}, review, {"stage_revision": "1", "status": "REVISE"})

    def test_assert_fixture_state_rejects_review_for_other_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, stage, review = self._write_state(Path(temporary))
            review.write_text("---\nstage: S02\nstage_revision: 1\nstatus: REVISE\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "fixture state mismatch"):
                assert_fixture_state(plan, "planning", "S01", "S01", {"Status": "REVIEW", "Revision": "1"}, stage, {"revision": "1"}, review, {"stage_revision": "1", "status": "REVISE"})

    def _write_state(self, root: Path) -> tuple[Path, Path, Path]:
        plan = root / "plan.md"
        stage = root / "stage.md"
        review = root / "review.md"
        plan.write_text("---\nstatus: planning\ncurrent_stage: S01\n---\n\n## Stage map\n\n### S01 — Test\n- Status: REVIEW\n- Revision: 1\n", encoding="utf-8")
        stage.write_text("---\nstage: S01\nstatus: REVIEW\nrevision: 1\n---\n", encoding="utf-8")
        review.write_text("---\nstage: S01\nstage_revision: 1\nstatus: REVISE\n---\n", encoding="utf-8")
        return plan, stage, review


if __name__ == "__main__":
    unittest.main()
