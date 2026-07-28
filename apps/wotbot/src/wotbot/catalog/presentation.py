from typing import Any

from wotbot.catalog.models import ThingRecord
from wotbot.catalog.store import serialize_document


def serialize_thing(
    record: ThingRecord,
    *,
    include_document: bool = False,
) -> dict[str, Any]:
    thing: dict[str, Any] = {
        "id": record.id,
        "title": record.title,
        "description": record.description,
        "tags": record.tags,
        "source": record.source,
    }

    if include_document:
        thing["document"] = serialize_document(record)

    return thing
