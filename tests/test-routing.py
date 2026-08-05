from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RoutingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyst = (ROOT / "agents/orchestrator-analyst.md").read_text(encoding="utf-8")
        cls.guide = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    def test_workflow_continues_without_test_modes(self):
        self.assertNotIn("MODE: STEP", self.analyst)
        self.assertNotIn("MODE: RUN", self.analyst)
        self.assertNotIn("PAUSED", self.analyst)
        self.assertIn("Continue through transitions until a user decision", self.analyst)
        self.assertIn("every other accepted status continues through a tool call", self.analyst)

    def test_questions_are_durable_before_follow_up(self):
        question = self.analyst.index("Discovery `QUESTIONS`")
        answer = self.analyst.index("mark it `answered`", question)
        follow_up = self.analyst.index("set `plan.md` to `discovery`", answer)
        self.assertLess(question, answer)
        self.assertLess(answer, follow_up)

    def test_stage_sequence_is_pass_gated(self):
        planner = self.analyst.index("`PROPOSED`, resumable `PLANNING`")
        reviewer = self.analyst.index("Stage `REVIEW`", planner)
        next_stage = self.analyst.index("A `PASS` stage selects", reviewer)
        self.assertLess(planner, reviewer)
        self.assertLess(reviewer, next_stage)
        self.assertIn("All stages at `PASS` produce `READY`", self.guide)

    def test_resume_uses_artifacts(self):
        self.assertIn("reconcile artifacts", self.analyst)
        self.assertIn("When an artifact already proves work completed", self.analyst)
        for path in ("discovery.md", "questions.md", "plan.md", "stages/<NN>-<slug>.md", "reviews/<NN>.md"):
            self.assertIn(path, self.guide)

    def test_stage_review_continues_until_pass(self):
        self.assertIn("every actionable `REVISE` creates the next positive revision", self.analyst)
        self.assertIn("revision count does not stop an actionable correction", self.analyst)
        self.assertIn("always continues through a new planner revision", self.guide)

    def test_every_routing_result_has_a_handler(self):
        for status in ("QUESTIONS", "READY_FOR_APPROVAL", "REVIEW", "PASS", "REVISE", "MAP_CHANGE_REQUIRED", "BLOCKED"):
            self.assertIn(status, self.analyst)
        self.assertIn("Итог: WAITING_INPUT|READY|BLOCKED", self.analyst)
        self.assertIn("APPROVE MAP CHANGE", self.analyst)

    def test_artifact_index_reconciliation_is_explicit(self):
        self.assertIn("reconciles to `REVIEW` without another planner call", self.analyst)
        self.assertIn("current `REVISE` review invokes the planner correction", self.analyst)
        self.assertIn("without another reviewer call", self.analyst)

    def test_access_blocker_can_resume(self):
        self.assertIn("A resumed `blocked` workflow rechecks its recorded action", self.analyst)
        self.assertIn("legacy revision-budget blocker", self.analyst)
        self.assertIn("returns to `discovery` in `FOLLOW_UP`", self.analyst)


if __name__ == "__main__":
    unittest.main()
