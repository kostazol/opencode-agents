from copy import deepcopy
import unittest

from orchestrator_core.protocol import ProtocolError
from orchestrator_core.traceability import validate_execution_graph
from tests.orchestrator_fixture import analysis_fixture


class TraceabilityTests(unittest.TestCase):
    def test_requirement_acceptance_must_stay_in_owning_stage(self):
        value = analysis_fixture()
        second = deepcopy(value["stages"][0])
        second.update(
            id="S02",
            title="Второй этап",
            slug="second-stage",
            depends_on=["S01"],
            requirements=[],
            nfrs=[],
            contracts_consumed=[],
            contracts_produced=[],
        )
        value["stages"].append(second)
        value["acceptance"][0]["stage"] = "S02"
        with self.assertRaisesRegex(ProtocolError, "owning stage"):
            validate_execution_graph(value)

    def test_contract_consumer_must_depend_on_internal_producer(self):
        value = analysis_fixture()
        value["contracts"][1]["terminal"] = False
        value["contracts"][1]["consumers"] = ["S02"]
        value["stages"].append(
            {
                "id": "S02",
                "title": "Потребитель",
                "slug": "consumer",
                "depends_on": [],
                "requirements": [],
                "nfrs": [],
                "contracts_consumed": ["CON-002"],
                "contracts_produced": [],
                "affected_area": "Library",
                "risks": [],
            }
        )
        with self.assertRaisesRegex(ProtocolError, "dependency graph"):
            validate_execution_graph(value)

    def test_decision_shape_is_closed(self):
        value = analysis_fixture()
        value["decisions"][0]["owner"] = "S01"
        with self.assertRaisesRegex(ProtocolError, "exactly id and non-empty text"):
            validate_execution_graph(value)


if __name__ == "__main__":
    unittest.main()
