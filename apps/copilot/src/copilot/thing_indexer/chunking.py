from __future__ import annotations

from typing import Any

from copilot.search.vector_store import SearchIndexDocument
from copilot.thing_indexer.summary_utils import ThingTDMetadata


def _schema_summary(schema: Any) -> str:
    if not isinstance(schema, dict):
        return str(schema)
    parts: list[str] = []
    if "type" in schema:
        parts.append(schema["type"])
    if "properties" in schema and isinstance(schema["properties"], dict):
        parts.append(f"[{', '.join(schema['properties'])}]")
    return " ".join(parts) if parts else str(schema)


def _semantic_type_labels(value: Any) -> list[str]:
    """Local names of semantic ``@type`` IRIs.

    Returns the human-meaningful class tokens so enrichment's semantic types become part of
    the embedded text and thus reachable by semantic ``things_search`` — not only SPARQL.
    """
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list):
        raw = [item for item in value if isinstance(item, str)]
    else:
        return []
    labels: list[str] = []
    for item in raw:
        local = item.rsplit(":", 1)[-1].rsplit("/", 1)[-1].rsplit("#", 1)[-1].strip()
        if local and local not in labels:
            labels.append(local)
    return labels


def _format_affordance_line(
    name: str,
    definition: dict[str, Any],
) -> str:
    parts: list[str] = [f"- {name}"]

    type_info = definition.get("type", "")
    unit = definition.get("unit", "")
    if type_info and unit:
        parts.append(f"({type_info}, {unit})")
    elif type_info:
        parts.append(f"({type_info})")
    elif unit:
        parts.append(f"({unit})")

    semantic_types = _semantic_type_labels(definition.get("@type"))
    if semantic_types:
        parts.append(f"[{', '.join(semantic_types)}]")

    if "input" in definition:
        parts.append(f"-> input: {_schema_summary(definition['input'])}")
    if "output" in definition:
        parts.append(f"-> output: {_schema_summary(definition['output'])}")

    return " ".join(parts)


def build_chunk_content(
    thing_td: dict[str, Any],
    device_summary: str,
) -> str:
    sections: list[str] = [device_summary]

    thing_types = _semantic_type_labels(thing_td.get("@type"))
    if thing_types:
        sections.append(f"Semantic types: {', '.join(thing_types)}")

    for td_key, label in [
        ("properties", "Properties"),
        ("actions", "Actions"),
        ("events", "Events"),
    ]:
        section = thing_td.get(td_key)
        if not isinstance(section, dict) or not section:
            continue

        lines: list[str] = [f"\n{label}:"]
        for name, definition in section.items():
            if not isinstance(name, str):
                continue
            defn = definition if isinstance(definition, dict) else {}
            lines.append(_format_affordance_line(name, defn))

        sections.append("\n".join(lines))

    return "\n".join(sections)


def generate_chunk(
    thing_td: dict[str, Any],
    td_metadata: ThingTDMetadata,
    device_summary: str,
    metadata: dict[str, Any],
) -> tuple[str, SearchIndexDocument]:
    content = build_chunk_content(thing_td, device_summary)
    return (
        td_metadata["id"],
        SearchIndexDocument(page_content=content, metadata=metadata),
    )
