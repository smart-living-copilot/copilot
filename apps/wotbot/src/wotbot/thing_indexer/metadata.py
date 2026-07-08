from __future__ import annotations

from typing import Any

from wotbot.core.time import utc_now
from wotbot.thing_indexer.summary_utils import ThingTDMetadata


def build_index_metadata(
    td_metadata: ThingTDMetadata,
    *,
    event_type: str | None,
    td_hash: str,
    prompt_version: str,
    summary_source: str,
    summary_model: str,
    indexed_at: str | None = None,
) -> dict[str, Any]:
    return {
        "id": td_metadata["id"],
        "title": td_metadata["title"],
        "description": td_metadata["description"],
        "tags": td_metadata["tags"],
        "locationCandidates": [],
        "propertyNames": td_metadata["propertyNames"],
        "actionNames": td_metadata["actionNames"],
        "eventNames": td_metadata["eventNames"],
        "eventType": event_type,
        "tdHash": td_hash,
        "indexedAt": indexed_at or utc_now().isoformat(),
        "promptVersion": prompt_version,
        "summarySource": summary_source,
        "summaryModel": summary_model,
    }
