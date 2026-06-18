import json
import unittest
from pathlib import Path

from copilot.virtual_things.contract_export import servient_contract_schema


class VirtualServientContractTestCase(unittest.TestCase):
    def test_committed_servient_schema_matches_exported_contract(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "virtual-servient"
            / "schema"
            / "servient-view.schema.json"
        )

        committed_schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(committed_schema, servient_contract_schema())


if __name__ == "__main__":
    unittest.main()
