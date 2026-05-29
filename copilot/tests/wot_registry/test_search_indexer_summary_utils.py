from copilot.search.indexer.summary_utils import (
    compute_td_hash,
    extract_td_metadata,
)


def test_compute_td_hash_ignores_transport_fields():
    thing_td = {
        "id": "urn:thing:alpha",
        "title": "Alpha Sensor",
        "description": "Kitchen air monitor",
        "tags": ["kitchen", "sensor"],
        "properties": {
            "temperature": {
                "type": "number",
                "description": "Ambient temperature",
            }
        },
    }

    transport_event = {
        **thing_td,
        "eventType": "update",
        "hash": "stored-document-hash",
    }

    assert compute_td_hash(thing_td) == compute_td_hash(transport_event)


def test_extract_td_metadata_basic():
    thing_td = {
        "id": "urn:thing:alpha",
        "title": "Alpha Sensor",
        "description": "Kitchen air monitor",
        "tags": ["kitchen", "sensor"],
        "properties": {
            "temperature": {
                "type": "number",
                "description": "Ambient temperature",
            },
            "humidity": {
                "type": "number",
                "description": "Relative humidity",
            },
        },
        "actions": {
            "calibrate": {
                "description": "Run calibration routine",
            },
        },
        "events": {
            "overheating": {
                "description": "Temperature exceeded threshold",
            },
        },
    }

    meta = extract_td_metadata(thing_td)

    assert meta["id"] == "urn:thing:alpha"
    assert meta["title"] == "Alpha Sensor"
    assert meta["description"] == "Kitchen air monitor"
    assert meta["tags"] == ["kitchen", "sensor"]
    assert meta["propertyNames"] == ["humidity", "temperature"]
    assert meta["actionNames"] == ["calibrate"]
    assert meta["eventNames"] == ["overheating"]


def test_extract_td_metadata_defaults():
    meta = extract_td_metadata({})

    assert meta["id"] == "unknown"
    assert meta["title"] == "unknown"
    assert meta["description"] == ""
    assert meta["tags"] == []
    assert meta["propertyNames"] == []
    assert meta["actionNames"] == []
    assert meta["eventNames"] == []
