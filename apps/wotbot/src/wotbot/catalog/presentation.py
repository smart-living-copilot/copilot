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
        "origin": {
            "kind": record.origin_kind,
            **(
                {
                    "provider": record.origin_provider,
                    "external_id": record.origin_external_id,
                    **({"source_id": record.origin_source_id} if record.origin_source_id else {}),
                }
                if record.origin_kind == "discovery"
                else {}
            ),
        },
    }

    if include_document:
        thing["document"] = serialize_document(record)

    return thing
