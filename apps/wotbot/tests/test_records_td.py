"""Unit tests for the virtual-record Thing Description builder.

These exercise the pure TD-building logic (no database), focusing on the
contract that declared action output schemas actually validate the payloads
the VirtualRecordStore returns.
"""

from __future__ import annotations

import unittest

from jsonschema import Draft202012Validator

from wotbot.jobs.records.td import build_virtual_record_td

RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "mood": {"type": "string"},
        "energy": {"type": "integer"},
        "note": {"type": "string"},
    },
    "required": ["mood", "energy"],
}


def _build():
    return build_virtual_record_td(
        thing_id="virtual:records:x",
        title="Wellbeing",
        description="Daily check-ins.",
        record_schema=RECORD_SCHEMA,
    )


def _validate(output_schema, sample):
    return sorted(Draft202012Validator(output_schema).iter_errors([sample]), key=str)


class VirtualRecordTdTest(unittest.TestCase):
    def test_generates_per_field_history_actions(self):
        actions = _build()["actions"]
        self.assertIn("query_records", actions)
        self.assertIn("query_property_history", actions)
        self.assertIn("history_energy", actions)
        self.assertIn("history_mood", actions)
        self.assertIn("history_note", actions)

    def test_query_records_output_matches_record_payload(self):
        # Mirrors VirtualRecordStore._record_payload (incl. nullable fields).
        payload = {
            "id": "r1",
            "thing_id": "virtual:records:x",
            "schema_version": 1,
            "source_job_id": "j1",
            "source_run_id": "run1",
            "recorded_at": "2026-06-05T20:00:00+00:00",
            "data": {"mood": "good", "energy": 4, "note": "ok"},
            "raw_input": None,
            "confidence": None,
        }
        out = _build()["actions"]["query_records"]["output"]
        self.assertEqual(_validate(out, payload), [])
        # Non-null raw_input / confidence are also valid.
        self.assertEqual(_validate(out, {**payload, "raw_input": "raw", "confidence": 0.9}), [])

    def test_history_output_matches_rows_and_enforces_value_type(self):
        actions = _build()["actions"]
        row = {
            "recorded_at": "2026-06-05T20:00:00+00:00",
            "value": 4,
            "source_run_id": "run1",
        }
        self.assertEqual(_validate(actions["history_energy"]["output"], row), [])
        self.assertEqual(_validate(actions["query_property_history"]["output"], row), [])
        # The per-field action pins the value to the field's scalar type.
        bad = {**row, "value": "not-an-int"}
        self.assertTrue(_validate(actions["history_energy"]["output"], bad))

    def test_history_input_enum_lists_bare_field_names(self):
        prop = _build()["actions"]["query_property_history"]["input"]["properties"]["property"]
        self.assertEqual(prop["enum"], ["energy", "mood", "note"])


if __name__ == "__main__":
    unittest.main()
