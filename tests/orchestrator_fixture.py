from orchestrator_core.controller import apply_event, create_state, reserve_next


def analysis_fixture() -> dict:
    return {
        "schema_version": 1,
        "request": {"summary": "Change a public library contract", "outcomes": ["New contract works"]},
        "change_surfaces": ["library"],
        "requirements": [
            {"id": "REQ-001", "text": "Add the contract", "stage": "S01", "acceptance": ["AC-001"], "scenarios": ["SCN-001"]}
        ],
        "nfrs": [
            {"id": "NFR-001", "text": "Keep compatibility", "category": "compatibility-migration", "stage": "S01", "acceptance": ["AC-002"], "scenarios": ["SCN-002"]}
        ],
        "decisions": [{"id": "DEC-001", "text": "Extend the current API"}],
        "contracts": [
            {"id": "CON-001", "text": "Existing input", "producer": None, "consumers": ["S01"], "external": True, "terminal": False},
            {"id": "CON-002", "text": "New output", "producer": "S01", "consumers": [], "external": False, "terminal": True},
        ],
        "acceptance": [
            {"id": "AC-001", "text": "New call works", "stage": "S01", "verification": "unit test"},
            {"id": "AC-002", "text": "Old call works", "stage": "S01", "verification": "compatibility test"},
        ],
        "scenarios": [
            {"id": "SCN-001", "text": "New call", "stage": "S01", "requirements": ["REQ-001"], "expected": "Result"},
            {"id": "SCN-002", "text": "Old call", "stage": "S01", "requirements": ["NFR-001"], "expected": "No regression"},
        ],
        "nfr_applicability": [
            {"category": "compatibility-migration", "status": "required", "evidence": "Library surface", "owner": "S01", "acceptance": ["AC-002"]}
        ],
        "stages": [
            {
                "id": "S01", "title": "Change contract", "slug": "change-contract", "depends_on": [],
                "requirements": ["REQ-001"], "nfrs": ["NFR-001"],
                "contracts_consumed": ["CON-001"], "contracts_produced": ["CON-002"],
                "affected_area": "Library", "risks": ["Breaking change"],
            }
        ],
        "assumptions": [],
        "non_goals": [],
    }


def event(action: dict, event_type: str, **payload) -> dict:
    return {"transition_id": action["transition_id"], "type": event_type, "payload": payload}


def advance_to_stage_planning() -> tuple[dict, dict]:
    analysis = analysis_fixture()
    state = create_state("sample")
    state, action = reserve_next(state)
    state, _ = apply_event(state, event(action, "discovery_result", status="READY_FOR_REVIEW", revision=1), analysis)
    state, action = reserve_next(state, analysis)
    state, _ = apply_event(state, event(action, "discovery_review_result", status="PASS", revision=1), analysis)
    state, action = reserve_next(state, analysis)
    state, _ = apply_event(state, event(action, "map_decision", decision="APPROVE"), analysis)
    return state, analysis
