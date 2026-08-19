#!/usr/bin/env python3

from copy import deepcopy
from pathlib import Path
import unittest

from failure_catalog import CHECKPOINT_ONLY_IDS, CATALOG_PATH, REQUIRED_IDS, SECURITY_IDS, load_catalog, valid_test_path, validate_catalog


class FailureCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()

    def test_catalog_is_valid_and_contains_all_stable_ids(self):
        self.assertEqual(tuple(scenario["id"] for scenario in self.catalog["scenarios"]), REQUIRED_IDS)

    def test_ids_must_be_complete_and_unique(self):
        missing = deepcopy(self.catalog)
        missing["scenarios"].pop()
        with self.assertRaisesRegex(ValueError, "complete and ordered"):
            validate_catalog(missing)
        duplicate = deepcopy(self.catalog)
        duplicate["scenarios"][-1]["id"] = duplicate["scenarios"][0]["id"]
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_catalog(duplicate)

    def test_enums_are_rejected_when_unknown(self):
        for field in ("test_layer", "coverage", "target_roadmap_phase"):
            with self.subTest(field=field):
                catalog = deepcopy(self.catalog)
                catalog["scenarios"][0][field] = "unknown"
                with self.assertRaisesRegex(ValueError, f"invalid {field}"):
                    validate_catalog(catalog)

    def test_covered_scenario_requires_existing_test(self):
        catalog = deepcopy(self.catalog)
        catalog["scenarios"][0]["existing_test_path"] = "tests/e2e_system/not-present.py"
        with self.assertRaisesRegex(ValueError, "covered test path does not exist"):
            validate_catalog(catalog)

    def test_covered_test_path_rejects_traversal_and_symlinks(self):
        catalog = deepcopy(self.catalog)
        catalog["scenarios"][0]["existing_test_path"] = "tests/../tests/e2e_system/test_harness.py"
        with self.assertRaisesRegex(ValueError, "covered test path does not exist"):
            validate_catalog(catalog)
        with self.subTest(case="symlink"):
            import tempfile
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "tests").mkdir()
                real = root / "tests/test_real.py"
                real.write_text("pass\n", encoding="utf-8")
                link = root / "tests/test_link.py"
                link.symlink_to(real)
                self.assertFalse(valid_test_path(root, "tests/test_link.py"))

    def test_uncovered_scenario_requires_target_and_reason_without_test_claim(self):
        scenario = self._scenario("task-cancellation")
        for field, value, diagnostic in (("target_roadmap_phase", "later", "invalid target_roadmap_phase"), ("defer_reason", "", "requires defer_reason"), ("existing_test_path", "tests/e2e_system/test_harness.py", "cannot claim a test")):
            with self.subTest(field=field):
                catalog = deepcopy(self.catalog)
                self._scenario_from(catalog, scenario["id"])[field] = value
                with self.assertRaisesRegex(ValueError, diagnostic):
                    validate_catalog(catalog)

    def test_phase_one_security_cannot_claim_workspace_guard_coverage(self):
        self.assertEqual(SECURITY_IDS, {scenario["id"] for scenario in self.catalog["scenarios"] if scenario["target_roadmap_phase"] == "phase-1"})
        catalog = deepcopy(self.catalog)
        scenario = self._scenario_from(catalog, "shell-mutation")
        scenario.update({"coverage": "covered", "test_layer": "deterministic-unit", "existing_test_path": "tests/e2e_system/test_workspace_guard.py", "defer_reason": None})
        with self.assertRaisesRegex(ValueError, "phase-1 security scenario must remain honestly uncovered"):
            validate_catalog(catalog)

    def test_checkpoint_cannot_claim_full_journey_coverage(self):
        self.assertEqual(CHECKPOINT_ONLY_IDS, {scenario["id"] for scenario in self.catalog["scenarios"] if scenario["test_layer"] == "live-transition-checkpoint"})
        catalog = deepcopy(self.catalog)
        scenario = self._scenario_from(catalog, "stale-artifact")
        scenario.update({"coverage": "covered", "defer_reason": None})
        with self.assertRaisesRegex(ValueError, "checkpoint coverage cannot claim a full journey|live transition checkpoint must be partial coverage"):
            validate_catalog(catalog)

    def test_loader_reads_canonical_json(self):
        self.assertEqual(load_catalog(Path(CATALOG_PATH))["schema_version"], 1)

    def _scenario(self, scenario_id):
        return self._scenario_from(self.catalog, scenario_id)

    @staticmethod
    def _scenario_from(catalog, scenario_id):
        return next(scenario for scenario in catalog["scenarios"] if scenario["id"] == scenario_id)


if __name__ == "__main__":
    unittest.main()
