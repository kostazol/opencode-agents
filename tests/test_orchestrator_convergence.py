import unittest

from orchestrator_core.controller import apply_event, create_state, reserve_next
from orchestrator_core.model import stages_from_analysis
from orchestrator_core.protocol import ProtocolError
from orchestrator_core.render import render_plan
from tests.orchestrator_fixture import advance_to_stage_planning, event, finding, three_stage_analysis


class ConvergenceTests(unittest.TestCase):
    def _review(self, state, analysis, revision, evidence="stage.md:1"):
        state, plan = reserve_next(state, analysis)
        state, _ = apply_event(state, event(plan, "stage_plan_result", status="REVIEW", revision=revision), analysis)
        state, review = reserve_next(state, analysis)
        return state, review, event(review, "stage_review_result", status="REVISE", revision=revision, findings=finding(evidence))

    def test_repeated_unchanged_findings_are_bounded(self):
        state, analysis = advance_to_stage_planning()
        state, review, revise = self._review(state, analysis, 1)
        state, _ = apply_event(state, revise, analysis)
        state, review, revise = self._review(state, analysis, 2)
        state, result = apply_event(state, revise, analysis)
        self.assertEqual((state["status"], result["reason"], state["stages"][0]["status"]), ("blocked", "no_semantic_progress", "proposed"))
        state, action = reserve_next(state, analysis)
        with self.assertRaisesRegex(ProtocolError, "feedback requires remarks"):
            apply_event(state, event(action, "blocker_resolution", decision="RETRY"), analysis)
        state, _ = apply_event(state, event(action, "blocker_resolution", decision="RETRY", remarks="Use the fallback contract"), analysis)
        state, action = reserve_next(state, analysis)
        self.assertEqual((action["action"], action["revision"], state["convergence"]), ("PLAN_STAGE", 3, {}))

    def test_changed_evidence_counts_as_progress(self):
        state, analysis = advance_to_stage_planning()
        state, _, revise = self._review(state, analysis, 1)
        state, _ = apply_event(state, revise, analysis)
        state, _, revise = self._review(state, analysis, 2, "stage.md:20")
        state, result = apply_event(state, revise, analysis)
        self.assertEqual((state["status"], result["status"], state["convergence"]["TECHNICAL:S01"]["repeats"]), ("planning", "planning", 1))

    def test_stage3_state_shape_is_upgraded_without_losing_progress(self):
        from orchestrator_core.model import validate_state
        state = create_state("sample")
        state["schema_version"] = 1
        state.pop("convergence")
        upgraded = validate_state(state)
        self.assertEqual((upgraded["schema_version"], upgraded["convergence"]), (1, {}))


class ReopeningTests(unittest.TestCase):
    def _passed_state(self):
        analysis = three_stage_analysis()
        state = create_state("sample")
        state.update(status="waiting_plan_approval", analysis_revision=1, analysis_status="approved", stages=stages_from_analysis(analysis))
        for number, stage in enumerate(state["stages"], start=1):
            stage.update(status="pass", revision=number, human_status="pass", human_revision=number)
        return state, analysis

    def test_user_feedback_reopens_only_affected_closure(self):
        state, analysis = self._passed_state()
        state, action = reserve_next(state, analysis)
        state, result = apply_event(state, event(action, "plan_decision", decision="FEEDBACK", scope="STAGES", remarks="Change stage two", reason="Contract changed", affected_stages=["S02"]), analysis)
        self.assertEqual(result["reopened"], ["S02", "S03"])
        self.assertEqual([stage["status"] for stage in state["stages"]], ["pass", "proposed", "proposed"])
        self.assertEqual([stage["revision"] for stage in state["stages"]], [1, 2, 3])

    def test_reviewer_reopen_waits_for_approval_and_can_be_rejected(self):
        state, analysis = self._passed_state()
        state.update(status="planning", current_stage="S03")
        state["stages"][2]["status"] = "review"
        state, action = reserve_next(state, analysis)
        state, result = apply_event(state, event(action, "stage_review_result", status="REOPEN", revision=3, reason="Upstream contract is wrong", affected_stages=["S02"]), analysis)
        self.assertEqual((result["affected"], state["status"]), (["S02", "S03"], "waiting_reopen_approval"))
        self.assertIn("- Affected: [S02, S03]", render_plan(state, analysis))
        state, approve = reserve_next(state, analysis)
        state, result = apply_event(state, event(approve, "reopen_decision", decision="REJECT"), analysis)
        self.assertEqual((state["status"], state["current_stage"], result["reopened"]), ("planning", "S03", []))
        self.assertEqual([stage["status"] for stage in state["stages"]], ["pass", "pass", "review"])

    def test_reviewer_reopen_preserves_unaffected_passed_stage(self):
        state, analysis = self._passed_state()
        state.update(status="planning", current_stage="S03")
        state["stages"][2]["status"] = "review"
        state, action = reserve_next(state, analysis)
        state, _ = apply_event(state, event(action, "stage_review_result", status="REOPEN", revision=3, reason="Upstream contract is wrong", affected_stages=["S02"]), analysis)
        state, approve = reserve_next(state, analysis)
        state, result = apply_event(state, event(approve, "reopen_decision", decision="APPROVE"), analysis)
        self.assertEqual(result["reopened"], ["S02", "S03"])
        self.assertEqual([stage["status"] for stage in state["stages"]], ["pass", "proposed", "proposed"])
        self.assertEqual(state["current_stage"], "S02")

    def test_reopen_proposal_rejects_changed_dependency_graph(self):
        state, analysis = self._passed_state()
        state.update(status="planning", current_stage="S03")
        state["stages"][2]["status"] = "review"
        state, action = reserve_next(state, analysis)
        state, _ = apply_event(state, event(action, "stage_review_result", status="REOPEN", revision=3, reason="Upstream contract is wrong", affected_stages=["S02"]), analysis)
        changed = three_stage_analysis()
        changed["stages"][2]["depends_on"] = ["S01"]
        changed["contracts"][2]["consumers"] = []
        changed["contracts"][2]["terminal"] = True
        changed["stages"][2]["contracts_consumed"] = []
        with self.assertRaisesRegex(ProtocolError, "state stage map does not match analysis"):
            reserve_next(state, changed)


if __name__ == "__main__":
    unittest.main()
