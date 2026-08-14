from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RoutingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyst = (ROOT / "agents/orchestrator-analyst.md").read_text(encoding="utf-8")
        cls.discovery = (ROOT / "agents/orchestrator-discovery.md").read_text(encoding="utf-8")
        cls.planner = (ROOT / "agents/orchestrator-stage-planner.md").read_text(encoding="utf-8")
        cls.reviewer = (ROOT / "agents/orchestrator-stage-reviewer.md").read_text(encoding="utf-8")
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
        planner = self.analyst.index("current-stage `PROPOSED`, resumable `PLANNING`")
        reviewer = self.analyst.index("Current stage `REVIEW`", planner)
        next_stage = self.analyst.index("A `PASS` stage selects", reviewer)
        self.assertLess(planner, reviewer)
        self.assertLess(reviewer, next_stage)
        self.assertIn("All human reviews at `PASS` wait for user `APPROVE PLAN`", self.guide)
        self.assertIn("Only `current_stage` may invoke a planner or reviewer", self.analyst)

    def test_resume_uses_artifacts(self):
        self.assertIn("reconcile artifacts", self.analyst)
        self.assertIn("finish matching artifact and index reconciliation", self.analyst)
        self.assertIn("resolve that exact path against `WORKFLOW_BASE`, read it first", self.analyst)
        self.assertIn("stays excluded from resolved path segments", self.analyst)
        for path in ("discovery.md", "questions.md", "plan.md", "stages/<NN>-<slug>.md", "reviews/<NN>.md"):
            self.assertIn(path, self.guide)

    def test_stage_review_continues_until_pass(self):
        self.assertIn("Every actionable `REVISE` first reserves next revision durably", self.analyst)
        self.assertIn("revision count does not stop an actionable correction", self.analyst)
        self.assertIn("always continues through a new planner revision", self.guide)

    def test_every_routing_result_has_a_handler(self):
        for status in ("QUESTIONS", "READY_FOR_APPROVAL", "REVIEW", "PASS", "REVISE", "MAP_CHANGE_REQUIRED", "BLOCKED", "HUMAN_REVIEW"):
            self.assertIn(status, self.analyst)
        self.assertIn("Итог: WAITING_INPUT|READY|BLOCKED", self.analyst)
        self.assertIn("APPROVE MAP CHANGE", self.analyst)
        self.assertIn("APPROVE PLAN", self.analyst)

    def test_artifact_index_reconciliation_is_explicit(self):
        self.assertIn("reconciles to `REVIEW` without another planner call", self.analyst)
        self.assertIn("recorded correction-source `REVISE` review at N invokes planner", self.analyst)
        self.assertIn("without another reviewer call", self.analyst)
        self.assertIn("reconcile human-review status to `REVIEW` without another planner call", self.analyst)
        self.assertIn("Process matching reviews without another reviewer call", self.analyst)
        self.assertIn("absolute routing precedence over every workflow state", self.analyst)

    def test_access_blocker_can_resume(self):
        self.assertIn("A resumed `blocked` workflow rechecks its recorded `Action`", self.analyst)
        self.assertIn("through the role that produced it", self.analyst)
        self.assertIn("legacy revision-budget blocker", self.analyst)
        self.assertIn("returns to `discovery` in `FOLLOW_UP`", self.analyst)

    def test_pass_means_reviewed_plan(self):
        self.assertIn("`PASS` certifies one stage plan for future implementation", self.analyst)
        self.assertIn("Planned product work still pending is a prerequisite", self.analyst)
        self.assertIn("Technical `PASS` certifies sufficient architecture", self.analyst)
        self.assertIn("Human-review `PASS` certifies faithful", self.analyst)

    def test_stage_plan_is_architecture_and_risk_guidance(self):
        for heading in ("## Architecture", "## Reference patterns", "## Required", "## Key contracts", "## Risks", "## Implementation outline", "## Required test scenarios", "## Acceptance signals", "## Verification", "## Implementation discretion", "## Non-goals"):
            self.assertIn(heading, self.planner)
        self.assertIn("Tie every item to repository evidence or a concrete material risk", self.planner)
        self.assertIn("every external or integration boundary", self.planner)
        self.assertIn("every business scenario and validation that implementation must test", self.planner)
        self.assertIn("`Вход/предусловия`, `Действие`, and `Ожидаемый результат`", self.planner)
        self.assertIn("test names, files, fixtures, mocks", self.planner)
        self.assertIn("the smallest coherent set of coarse implementation actions", self.planner)
        self.assertIn("reversible local classes, methods, files, and test organization", self.planner)
        self.assertIn("record `none` and the closest applicable convention", self.discovery)
        self.assertIn("Keep canonical `Consumes` and `Produces` fields for every stage", self.discovery)
        self.assertIn("affected system area, primary risks, consumed and produced contracts", self.analyst)

    def test_reviewer_gates_material_detail_not_document_volume(self):
        self.assertIn("Review planning quality and human-review fidelity", self.reviewer)
        self.assertIn("observable acceptance signal and proportionate verification level", self.reviewer)
        self.assertIn("Missing exhaustive file lists", self.reviewer)
        self.assertIn("unsupported precision constrains implementation without evidence", self.reviewer)
        self.assertIn("every mandatory constraint and prohibition", self.reviewer)
        self.assertIn("every material approved success, alternative, rejection, boundary", self.reviewer)
        self.assertIn("Missing business-behavior coverage is a finding", self.reviewer)
        self.assertIn("Mandatory business scenarios and validations remain required", self.reviewer)

    def test_results_require_semantic_validation(self):
        self.assertIn("compact block alone", self.analyst)
        self.assertIn("implementation-work blockers receive one fresh corrective call", self.analyst)
        self.assertIn("discovery may also report a material decision", self.analyst)
        self.assertIn("`PASS` requires zero findings and passing checks", self.analyst)
        self.assertIn("`REVISE` requires actionable current-stage findings", self.analyst)
        self.assertIn("`MAP_CHANGE_REQUIRED` requires evidence", self.analyst)
        self.assertIn("`BLOCKED` requires an allowed reason and exact action", self.analyst)

    def test_handoffs_are_path_only(self):
        self.assertEqual(self.analyst.count("path-only handoff"), 2)
        self.assertIn("containing mode, `WORKFLOW_BASE`, stage ID, indexed target revision, `plan.md`, `discovery.md`", self.analyst)
        self.assertIn("current stage ID, technical stage-file path", self.analyst)

    def test_primary_delegates_product_rechecks(self):
        self.assertIn("instead of inspecting product paths itself", self.analyst)
        self.assertIn("recorded access, safety, or decision action is satisfied", self.analyst)
        for field in ("`Producer`", "`Transition`", "`Source`", "`Evidence`", "`Action`"):
            self.assertIn(field, self.analyst)

    def test_human_readable_artifacts_use_russian(self):
        for content in (self.analyst, self.guide):
            self.assertTrue("по-русски" in content or "use Russian" in content)

    def test_human_reviews_gate_ready(self):
        self.assertIn("stages/<NN>-<slug>.human-review.md", self.analyst)
        self.assertIn("reviews/<NN>-human-review.md", self.analyst)
        self.assertIn("When every human review is `PASS`", self.analyst)
        self.assertIn("`APPROVE PLAN` sets `status: ready`", self.analyst)
        self.assertIn("append it verbatim to `feedback.md`", self.analyst)
        self.assertIn("PLAN_FEEDBACK", self.discovery)
        self.assertIn("latest pending feedback batch invokes", self.analyst)
        self.assertIn("append it verbatim to `feedback.md` as the next revision", self.analyst)
        self.assertIn("preserve every unaffected stage status, revision", self.discovery)
        self.assertIn("instead of reinitializing the whole map", self.discovery)
        self.assertIn("preserve or regenerate canonical future output paths", self.discovery)
        self.assertIn("Stage and human-review revisions stay monotonic", self.analyst)
        self.assertIn("keeps the feedback batch `pending`", self.analyst)
        self.assertIn("record durable mode `PLAN_FEEDBACK`", self.discovery)
        self.assertIn("Before entering or resuming `waiting-plan-approval`", self.analyst)
        self.assertIn("human review exposed a technical-plan mismatch", self.analyst)
        self.assertIn("`feedback.md` uses frontmatter `latest_revision: N`", self.discovery)
        self.assertIn("exactly matches the indexed technical revision", self.analyst)
        self.assertIn("already reserved indexed revision `N>1`", self.analyst)
        self.assertIn("resumed `PLAN_FEEDBACK`, incorporate every recorded answer", self.discovery)
        self.assertIn("Affected stages: unknown|[SNN, SNN]", self.discovery)

    def test_human_review_has_fidelity_gate(self):
        for heading in ("## Что я получу после этапа", "## Как это будет выглядеть в работе", "## Что именно будет сделано", "## Чего после этапа ещё не будет", "## Что важно подтвердить перед реализацией", "## Как принять готовую реализацию", "## Статус"):
            self.assertIn(heading, self.planner)
        self.assertIn("faithful coverage of every user-visible outcome", self.reviewer)
        self.assertIn("`stage_revision` equal to the human-review revision", self.reviewer)
        self.assertIn("First reservation and planner invocation form one atomic workflow transition", self.analyst)
        self.assertIn("read the exact indexed human-review and human-review review paths", self.analyst)
        self.assertIn("Correction source revision: N", self.analyst)
        self.assertIn("Reserve a revision once", self.analyst)
        self.assertIn("During feedback-driven approval, any other user remarks", self.analyst)
        self.assertIn("bare `RESUME: <path>`", self.analyst)
        self.assertIn("awaits user `APPROVE PLAN`", self.planner)


if __name__ == "__main__":
    unittest.main()
