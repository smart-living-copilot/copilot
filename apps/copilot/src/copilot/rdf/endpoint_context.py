from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from copilot.catalog.models import Thing
from copilot.rdf.store import sparql_query_kind

_EXAMPLE_QUERY_KEYS = (
    "slc:exampleQueries",
    "exampleQueries",
    "https://smart-living-copilot.example/vocab#exampleQueries",
)
_SUPPORTED_LANGUAGE_KEYS = (
    "sd:supportedLanguage",
    "supportedLanguage",
    "http://www.w3.org/ns/sparql-service-description#supportedLanguage",
    "https://www.w3.org/ns/sparql-service-description#supportedLanguage",
)
_VOID_KEYS = {
    "vocabulary": (
        "void:vocabulary",
        "vocabulary",
        "http://rdfs.org/ns/void#vocabulary",
    ),
    "class": (
        "void:class",
        "class",
        "http://rdfs.org/ns/void#class",
    ),
    "property": (
        "void:property",
        "property",
        "http://rdfs.org/ns/void#property",
    ),
    "classPartition": (
        "void:classPartition",
        "classPartition",
        "http://rdfs.org/ns/void#classPartition",
    ),
    "propertyPartition": (
        "void:propertyPartition",
        "propertyPartition",
        "http://rdfs.org/ns/void#propertyPartition",
    ),
}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _value_at(document: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in document:
            return document[key]
    return None


def _compact_value(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) <= {"@id"} and isinstance(value.get("@id"), str):
            return value["@id"]
        return {
            key: _compact_value(item)
            for key, item in value.items()
            if isinstance(key, str) and key != "@context"
        }
    if isinstance(value, list):
        return [_compact_value(item) for item in value]
    return value


def _extract_prefixes(context: Any) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for item in _as_list(context):
        if isinstance(item, dict):
            for key, value in item.items():
                if not isinstance(key, str) or key.startswith("@"):
                    continue
                iri = value
                if isinstance(value, dict):
                    iri = value.get("@id")
                if isinstance(iri, str) and (iri.endswith(("/", "#")) or ":" in iri):
                    prefixes[key] = iri
    return prefixes


def extract_example_queries(document: dict[str, Any]) -> list[dict[str, str]]:
    examples = _value_at(document, _EXAMPLE_QUERY_KEYS)
    normalized: list[dict[str, str]] = []
    for item in _as_list(examples):
        if not isinstance(item, dict):
            normalized.append({"intent": "", "query": ""})
            continue
        intent = item.get("intent")
        query = item.get("query")
        normalized.append(
            {
                "intent": intent if isinstance(intent, str) else "",
                "query": query if isinstance(query, str) else "",
            }
        )
    return normalized


def validate_example_queries(document: dict[str, Any]) -> None:
    examples = _value_at(document, _EXAMPLE_QUERY_KEYS)
    if examples is None:
        return
    if not isinstance(examples, list):
        raise ValueError("slc:exampleQueries must be a list")

    for index, item in enumerate(examples):
        if not isinstance(item, dict):
            raise ValueError(f"slc:exampleQueries[{index}] must be an object")
        intent = item.get("intent")
        query = item.get("query")
        if not isinstance(intent, str) or not intent.strip():
            raise ValueError(f"slc:exampleQueries[{index}].intent must be a non-empty string")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"slc:exampleQueries[{index}].query must be a non-empty string")
        sparql_query_kind(query)


def endpoint_context_from_document(
    *,
    thing_id: str,
    document: dict[str, Any],
) -> dict[str, Any]:
    void_context: dict[str, Any] = {}
    for label, keys in _VOID_KEYS.items():
        value = _value_at(document, keys)
        if value is not None:
            void_context[label] = _compact_value(value)

    return {
        "id": thing_id,
        "title": document.get("title") if isinstance(document.get("title"), str) else thing_id,
        "description": document.get("description")
        if isinstance(document.get("description"), str)
        else "",
        "tags": [str(tag) for tag in document.get("tags", []) if isinstance(tag, str)],
        "prefixes": _extract_prefixes(document.get("@context")),
        "supportedLanguage": _compact_value(_value_at(document, _SUPPORTED_LANGUAGE_KEYS)),
        "void": void_context,
        "exampleQueries": extract_example_queries(document),
    }


def load_endpoint_contexts(session: Session, endpoint_ids: list[str]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for endpoint_id in endpoint_ids:
        thing = session.get(Thing, endpoint_id)
        if thing is None:
            raise ValueError(f"Endpoint Thing not found: {endpoint_id}")
        document = thing.document if isinstance(thing.document, dict) else {}
        contexts.append(endpoint_context_from_document(thing_id=endpoint_id, document=document))
    return contexts
