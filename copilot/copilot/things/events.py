from copilot.things.models import ThingRecord
from copilot.things.store import serialize_document


def build_change_event(event_type: str, record: ThingRecord) -> dict[str, object]:
    return {
        **serialize_document(record),
        "eventType": event_type,
        "hash": record.document_hash,
    }


def build_remove_event(thing_id: str) -> dict[str, str]:
    return {
        "eventType": "remove",
        "id": thing_id,
    }
