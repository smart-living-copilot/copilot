import json
from typing import Any


def parse_stream_event(fields: dict[str, str]) -> dict[str, Any]:
    payload = fields.get("event_json", "")
    if not payload:
        raise ValueError("Thing event stream entry is missing 'event_json'.")

    try:
        event = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Thing event stream entry contains invalid JSON: {exc}"
        ) from exc

    if not isinstance(event, dict):
        raise ValueError("Thing event stream entry must decode to an object.")

    return event
