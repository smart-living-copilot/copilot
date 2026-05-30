import pytest

from copilot.thing_indexer.stream_utils import parse_stream_event


def test_parse_stream_event_rejects_missing_event_json():
    with pytest.raises(ValueError, match="missing 'event_json'"):
        parse_stream_event({})


def test_parse_stream_event_rejects_invalid_json():
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_stream_event({"event_json": "not-json"})


def test_parse_stream_event_rejects_non_object_payload():
    with pytest.raises(ValueError, match="must decode to an object"):
        parse_stream_event({"event_json": '["not", "an", "object"]'})
