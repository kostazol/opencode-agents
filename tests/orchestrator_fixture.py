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


def finding(evidence: str = "stage.md:1") -> list[dict]:
    return [{"code": "MISSING-CASE", "scope": "S01", "message": "Handle the missing case", "evidence": evidence}]


def three_stage_analysis() -> dict:
    value = analysis_fixture()
    value["contracts"][1].update(consumers=["S02"], terminal=False)
    value["contracts"] += [
        {"id": "CON-003", "text": "Second output", "producer": "S02", "consumers": ["S03"], "external": False, "terminal": False},
        {"id": "CON-004", "text": "Final output", "producer": "S03", "consumers": [], "external": False, "terminal": True},
    ]
    for number in (2, 3):
        stage_id = f"S{number:02d}"
        req_id = f"REQ-{number:03d}"
        ac_id = f"AC-{number + 1:03d}"
        scn_id = f"SCN-{number + 1:03d}"
        value["requirements"].append({"id": req_id, "text": f"Implement stage {number}", "stage": stage_id, "acceptance": [ac_id], "scenarios": [scn_id]})
        value["acceptance"].append({"id": ac_id, "text": f"Stage {number} works", "stage": stage_id, "verification": "unit test"})
        value["scenarios"].append({"id": scn_id, "text": f"Stage {number} path", "stage": stage_id, "requirements": [req_id], "expected": "Result"})
    value["stages"] += [
        {
            "id": "S02", "title": "Second stage", "slug": "second-stage", "depends_on": ["S01"],
            "requirements": ["REQ-002"], "nfrs": [], "contracts_consumed": ["CON-002"],
            "contracts_produced": ["CON-003"], "affected_area": "Library", "risks": [],
        },
        {
            "id": "S03", "title": "Third stage", "slug": "third-stage", "depends_on": ["S02"],
            "requirements": ["REQ-003"], "nfrs": [], "contracts_consumed": ["CON-003"],
            "contracts_produced": ["CON-004"], "affected_area": "Library", "risks": [],
        },
    ]
    return value
