from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from orchestrator_core.legacy import parse_legacy_plan
from orchestrator_core.protocol import (
    ProtocolError,
    affected_stage_closure,
    load_json,
    required_nfr_categories,
    validate_analysis,
)


def valid_analysis() -> dict:
    return {
        "schema_version": 1,
        "request": {"summary": "Добавить надёжную обработку событий", "outcomes": ["События обрабатываются один раз"]},
        "change_surfaces": ["api", "data"],
        "requirements": [
            {"id": "REQ-001", "text": "Принять событие", "stage": "S01", "acceptance": ["AC-001"], "scenarios": ["SCN-001"]},
            {"id": "REQ-002", "text": "Обработать событие", "stage": "S02", "acceptance": ["AC-002"], "scenarios": ["SCN-002"]},
        ],
        "nfrs": [
            {"id": "NFR-001", "text": "Не создавать дубль", "category": "data-integrity-concurrency", "stage": "S02", "acceptance": ["AC-003"], "scenarios": ["SCN-003"]},
        ],
        "decisions": [{"id": "DEC-001", "text": "Использовать idempotency key"}],
        "contracts": [
            {"id": "CON-001", "text": "Входное событие", "producer": None, "consumers": ["S01"], "external": True, "terminal": False},
            {"id": "CON-002", "text": "Нормализованное событие", "producer": "S01", "consumers": ["S02"], "external": False, "terminal": False},
            {"id": "CON-003", "text": "Результат обработки", "producer": "S02", "consumers": [], "external": False, "terminal": True},
        ],
        "acceptance": [
            {"id": "AC-001", "text": "API принимает корректное событие", "stage": "S01", "verification": "integration test"},
            {"id": "AC-002", "text": "Worker сохраняет результат", "stage": "S02", "verification": "integration test"},
            {"id": "AC-003", "text": "Повтор не создаёт дубль", "stage": "S02", "verification": "concurrency test"},
            {"id": "AC-004", "text": "Latency измерена", "stage": "S01", "verification": "load smoke"},
            {"id": "AC-005", "text": "Recovery проверен", "stage": "S02", "verification": "failure test"},
            {"id": "AC-006", "text": "Security boundary проверена", "stage": "S01", "verification": "authorization test"},
            {"id": "AC-007", "text": "Compatibility проверена", "stage": "S01", "verification": "contract test"},
            {"id": "AC-008", "text": "Diagnostics доступны", "stage": "S02", "verification": "log assertion"},
        ],
        "scenarios": [
            {"id": "SCN-001", "text": "Корректный запрос", "stage": "S01", "requirements": ["REQ-001"], "expected": "202"},
            {"id": "SCN-002", "text": "Обработка", "stage": "S02", "requirements": ["REQ-002"], "expected": "Результат сохранён"},
            {"id": "SCN-003", "text": "Повтор", "stage": "S02", "requirements": ["NFR-001"], "expected": "Одна запись"},
        ],
        "nfr_applicability": [
            {"category": "performance-capacity", "status": "required", "evidence": "API path", "owner": "S01", "acceptance": ["AC-004"]},
            {"category": "availability-recovery", "status": "required", "evidence": "Worker and database", "owner": "S02", "acceptance": ["AC-005"]},
            {"category": "security-privacy-compliance", "status": "required", "evidence": "External API", "owner": "S01", "acceptance": ["AC-006"]},
            {"category": "data-integrity-concurrency", "status": "required", "evidence": "Retryable events", "owner": "S02", "acceptance": ["AC-003"]},
            {"category": "compatibility-migration", "status": "required", "evidence": "Public contract", "owner": "S01", "acceptance": ["AC-007"]},
            {"category": "observability-support", "status": "required", "evidence": "Async processing", "owner": "S02", "acceptance": ["AC-008"]},
        ],
        "stages": [
            {
                "id": "S01",
                "title": "Приём события",
                "slug": "accept-event",
                "depends_on": [],
                "requirements": ["REQ-001"],
                "nfrs": [],
                "contracts_consumed": ["CON-001"],
                "contracts_produced": ["CON-002"],
                "affected_area": "API",
                "risks": ["Некорректная нормализация"],
            },
            {
                "id": "S02",
                "title": "Обработка",
                "slug": "process-event",
                "depends_on": ["S01"],
                "requirements": ["REQ-002"],
                "nfrs": ["NFR-001"],
                "contracts_consumed": ["CON-002"],
                "contracts_produced": ["CON-003"],
                "affected_area": "Worker",
                "risks": ["Дубли при retry"],
            },
        ],
        "assumptions": ["Database supports unique indexes"],
        "non_goals": ["Изменение transport"],
    }


class ProtocolTests(unittest.TestCase):
    def test_valid_analysis_and_affected_closure(self):
        value = validate_analysis(valid_analysis())
        self.assertEqual(value["stages"][1]["id"], "S02")
        self.assertEqual(affected_stage_closure(value, ["S01"]), ["S01", "S02"])
        self.assertEqual(affected_stage_closure(value, ["S02"]), ["S02"])

    def test_required_nfrs_are_derived_from_surfaces(self):
        categories = required_nfr_categories(["api", "data"])
        self.assertIn("security-privacy-compliance", categories)
        self.assertIn("data-integrity-concurrency", categories)

    def test_requirement_without_acceptance_is_rejected(self):
        value = valid_analysis()
        value["requirements"][0]["acceptance"] = []
        with self.assertRaisesRegex(ProtocolError, "requires at least one acceptance"):
            validate_analysis(value)

    def test_contract_without_producer_or_consumer_is_rejected(self):
        value = valid_analysis()
        value["contracts"][1]["producer"] = None
        with self.assertRaisesRegex(ProtocolEr, "internal contract requires a producer"):
            validate_analysis(value)
        value = valid_analysis()
        value["contracts"][1]["consumers"] = []
        with self.assertRaisesRegex(ProtocolError, "must be terminal"):
            validate_analysis(value)

    def test_stage_dependency_must_reference_earlier_stage(self):
        value = valid_analysis()
        value["stages"][0]["depends_on"] = ["S02"]
        with self.assertRaisesRegex(ProtocolError, "earlier stages"):
            validate_analysis(value)

    def test_surface_implied_nfr_cannot_be_omitted(self):
        value = valid_analysis()
        value["nfr_applicability"] = [item for item in value["nfr_applicability"] if item["category"] != "security-privacy-compliance"]
        with self.assertRaisesRegex(ProtocolError, "missing categories"):
            validate_analysis(value)

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "analysis.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaisesRegex(ProtocolError, "duplicate JSON key"):
                load_json(path)

    def test_validation_does_not_mutate_input(self):
        value = valid_analysis()
        original = deepcopy(value)
        validate_analysis(value)
        self.assertEqual(value, original)

    def test_legacy_plan_migrates_human_review_paths(self):
        content = """---
status: planning
current_stage: S01
---
# Plan

## Stage map

### S01 — Первый этап
- Status: REVIEW
- Revision: 2
- Depends on: none
- Affected area: API
- Primary risks: none
- Consumes: none
- Produces: none
- Details: stages/01-first.md
- Review: reviews/01.md
"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.md"
            path.write_text(content, encoding="utf-8")
            migrated = parse_legacy_plan(path)
        stage = migrated["stages"][0]
        self.assertEqual(stage["human_review"], "stages/01-first.human-review.md")
        self.assertEqual(stage["human_review_review"], "reviews/01-human-review.md")
        self.assertTrue(migrated["requires_analysis_migration"])


if __name__ == "__main__":
    unittest.main()
