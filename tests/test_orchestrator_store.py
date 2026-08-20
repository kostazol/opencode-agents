import json
from pathlib import Path
import tempfile
import unittest

from orchestrator_core.controller import apply_event, create_state, reserve_next
from orchestrator_core.io import atomic_write
from orchestrator_core.protocol import ProtocolError
from orchestrator_core.render import render_plan
from orchestrator_core.store import WorkflowStore
from tests.orchestrator_fixture import analysis_fixture, event


class StoreTests(unittest.TestCase):
    def test_reserve_persists_one_action_and_one_journal_entry(self):
        with tempfile.TemporaryDirectory() as root:
            store = WorkflowStore(Path(root), "sample")
            state, action = store.reserve(expected_state_revision=0)
            repeated, same = store.reserve(expected_state_revision=state["state_revision"])
            self.assertEqual((action["action"], same, repeated), ("DISCOVER", action, state))
            self.assertTrue(store.state_path.is_file() and store.plan_path.is_file())
            self.assertEqual(len(store.journal_path.read_text().splitlines()), 1)

    def test_recovery_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            store = WorkflowStore(Path(root), "sample")
            state = create_state("sample")
            transaction = {
                "schema_version": 1,
                "state": state,
                "plan": render_plan(state),
                "journal": {"entry_id": "recover:0", "timestamp": "2026-01-01T00:00:00+00:00", "action": "apply", "state_revision": 0, "transition_id": None, "detail": {}},
            }
            store.internal.mkdir(parents=True)
            atomic_write(store.transaction_path, (json.dumps(transaction) + "\n").encode())
            self.assertTrue(store.recover())
            self.assertFalse(store.recover())
            self.assertEqual(len(store.journal_path.read_text().splitlines()), 1)

    def test_stale_client_and_concurrent_writer_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            first = WorkflowStore(Path(root), "sample")
            second = WorkflowStore(Path(root), "sample")
            first.reserve(expected_state_revision=0)
            with self.assertRaisesRegex(ProtocolError, "state revision conflict"):
                first.reserve(expected_state_revision=0)
            with first.lock():
                with self.assertRaisesRegex(ProtocolError, "already being advanced"):
                    with second.lock(timeout=0.05):
                        pass

    def test_legacy_passed_stage_is_preserved_after_typed_approval(self):
        legacy = """---
status: ready
current_stage: none
---
# Plan

## Stage map

### S01 — Change contract
- Status: PASS
- Revision: 3
- Depends on: none
- Affected area: Library
- Primary risks: Breaking change
- Consumes: CON-001
- Produces: CON-002
- Details: stages/01-change-contract.md
- Review: reviews/01.md
- Human review: stages/01-change-contract.human-review.md
- Human review revision: 2
- Human review status: PASS
- Human review review: reviews/01-human-review.md
"""
        with tempfile.TemporaryDirectory() as root:
            store = WorkflowStore(Path(root), "sample")
            store.root.mkdir(parents=True)
            store.plan_path.write_text(legacy)
            state = store.load_state()
            self.assertTrue(state["legacy_migrated"])
            state.update(status="waiting_map_approval", analysis_revision=1, analysis_status="reviewed")
            state, action = reserve_next(state, analysis_fixture())
            state, _ = apply_event(state, event(action, "map_decision", decision="APPROVE"), analysis_fixture())
            self.assertEqual((state["legacy_migrated"], state["stages"][0]["revision"], state["stages"][0]["status"]), (False, 3, "pass"))
            self.assertTrue((store.internal / "legacy-plan.md").is_file())

    def test_request_path_cannot_escape_base(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ProtocolError):
                WorkflowStore(Path(root), "../escape")


if __name__ == "__main__":
    unittest.main()
