from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .events import apply_event
from .io import append_jsonl_once, atomic_write, exclusive_lock, json_bytes, recover_transaction
from .migration import legacy_to_state
from .model import REQUEST_ID, new_state, validate_state
from .protocol import ProtocolError, load_json
from .render import render_plan
from .routing import reserve_next
from .traceability import validate_execution_graph


class WorkflowStore:
    def __init__(self, workflow_base: Path, request_id: str):
        if REQUEST_ID.fullmatch(request_id) is None:
            raise ProtocolError("request_id", "invalid request identifier", request_id)
        self.workflow_base = workflow_base.expanduser().resolve()
        self.root = (self.workflow_base / "1_orchestrator" / request_id).resolve()
        if self.root.parent != (self.workflow_base / "1_orchestrator").resolve():
            raise ProtocolError("workflow_root", "request path escapes workflow base", str(self.root))
        self.request_id = request_id
        self.internal = self.root / ".orchestrator"
        self.state_path = self.internal / "state.json"
        self.journal_path = self.internal / "journal.jsonl"
        self.transaction_path = self.internal / "transaction.json"
        self.lock_path = self.internal / "lock"
        self.plan_path = self.root / "plan.md"
        self.analysis_path = self.root / "analysis.json"

    def _ensure_root(self) -> None:
        self.internal.mkdir(parents=True, exist_ok=True)
        if self.root.resolve().parent != (self.workflow_base / "1_orchestrator").resolve():
            raise ProtocolError("workflow_root", "resolved request path escapes workflow base")

    def lock(self, *, timeout: float = 5.0, stale_after: float = 300.0):
        self._ensure_root()
        return exclusive_lock(self.lock_path, timeout=timeout, stale_after=stale_after)

    def recover(self) -> bool:
        self._ensure_root()
        return recover_transaction(self.transaction_path, self.state_path, self.plan_path, self.journal_path)

    def load_state(self) -> dict[str, Any]:
        self._ensure_root()
        self.recover()
        if self.state_path.exists():
            return validate_state(load_json(self.state_path))
        if self.plan_path.exists():
            backup = self.internal / "legacy-plan.md"
            if not backup.exists():
                atomic_write(backup, self.plan_path.read_bytes())
            return legacy_to_state(self.plan_path, self.request_id)
        return new_state(self.request_id)

    def load_analysis(self) -> dict[str, Any] | None:
        return validate_execution_graph(load_json(self.analysis_path)) if self.analysis_path.exists() else None

    def _journal(self, action: str, state: Mapping[str, Any], detail: Mapping[str, Any]) -> dict[str, Any]:
        transition_id = detail.get("transition_id")
        return {
            "entry_id": f"{transition_id or 'state'}:{action}:{state['state_revision']}",
            "timestamp": datetime.now(timezone.utc).isoformat(), "action": action,
            "state_revision": state["state_revision"], "transition_id": transition_id,
            "detail": deepcopy(dict(detail)),
        }

    def _commit(self, state: Mapping[str, Any], analysis: Mapping[str, Any] | None, journal: Mapping[str, Any]) -> None:
        cross_check = analysis if analysis is not None and state.get("stages") and not state.get("legacy_migrated") else None
        validated = validate_state(state, cross_check)
        plan = render_plan(validated, analysis)
        transaction = {"schema_version": 1, "state": validated, "plan": plan, "journal": dict(journal)}
        atomic_write(self.transaction_path, json_bytes(transaction))
        atomic_write(self.state_path, json_bytes(validated))
        atomic_write(self.plan_path, plan.encode(), 0o644)
        append_jsonl_once(self.journal_path, journal)
        self.transaction_path.unlink(missing_ok=True)

    def reserve(self, *, expected_state_revision: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        with self.lock():
            state, analysis = self.load_state(), self.load_analysis()
            next_state, action = reserve_next(state, analysis, expected_state_revision=expected_state_revision)
            if next_state != state:
                self._commit(next_state, analysis, self._journal("reserve", next_state, action))
            return next_state, action

    def apply(self, event: Mapping[str, Any], *, expected_state_revision: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        with self.lock():
            state, analysis = self.load_state(), self.load_analysis()
            next_state, result = apply_event(state, event, analysis, expected_state_revision=expected_state_revision)
            if next_state != state:
                detail = {"transition_id": event.get("transition_id"), "event_type": event.get("type"), "result": result}
                self._commit(next_state, analysis, self._journal("apply", next_state, detail))
            return next_state, result

    def validate(self) -> dict[str, Any]:
        with self.lock():
            state, analysis = self.load_state(), self.load_analysis()
            cross_check = analysis if analysis is not None and state["stages"] and not state["legacy_migrated"] else None
            validate_state(state, cross_check)
            issues: list[str] = []
            expected = render_plan(state, analysis)
            if self.plan_path.exists() and self.plan_path.read_text(encoding="utf-8") != expected:
                issues.append("plan.md differs from deterministic rendering")
            if state["analysis_status"] in {"review", "reviewed", "approved"} and analysis is None:
                issues.append("analysis.json is required by current state")
            return {"valid": not issues, "state_revision": state["state_revision"], "status": state["status"], "pending": state["pending"], "issues": issues}
