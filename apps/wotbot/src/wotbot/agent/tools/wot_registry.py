"""LangGraph tools for the WoT registry and runtime."""

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from langchain_core.tools import tool
from sqlalchemy.orm import Session

from wotbot.catalog import serialize_thing, validate_document
from wotbot.catalog.ids import decode_thing_id
from wotbot.catalog.service import ThingCatalogQueryService, ThingCatalogWriteService
from wotbot.clients.rdf_service import RdfServiceClient
from wotbot.clients.wot_runtime import WotRuntimeClient
from wotbot.core.config import get_settings as get_registry_settings
from wotbot.core.database import get_session_factory
from wotbot.rdf.schema import CLASSES_QUERY, PREDICATES_QUERY, summarize_schema
from wotbot.search import get_active_search_service


def _tool_error(exc: HTTPException) -> ValueError:
    detail = exc.detail
    if isinstance(detail, str) and detail.strip():
        return ValueError(detail)
    return ValueError(f"Request failed with status {exc.status_code}")


async def _run_with_session(operation: Callable[[Session], dict[str, Any]]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        session_factory = get_session_factory()
        with session_factory() as session:
            try:
                return operation(session)
            except HTTPException as exc:
                raise _tool_error(exc) from exc

    return await asyncio.to_thread(run)


def _runtime_client() -> WotRuntimeClient:
    return WotRuntimeClient(get_registry_settings())


def _rdf_client() -> RdfServiceClient:
    return RdfServiceClient(get_registry_settings())


def _thing_summary(payload: dict[str, Any]) -> dict[str, Any]:
    document = payload.get("document")
    properties = document.get("properties", {}) if isinstance(document, dict) else {}
    actions = document.get("actions", {}) if isinstance(document, dict) else {}
    events = document.get("events", {}) if isinstance(document, dict) else {}
    return {
        **payload,
        "property_count": len(properties) if isinstance(properties, dict) else 0,
        "action_count": len(actions) if isinstance(actions, dict) else 0,
        "event_count": len(events) if isinstance(events, dict) else 0,
    }


def _bounded_int(value: int | None, *, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    return min(max(value, minimum), maximum)


def _decoded_runtime_value(result: Any) -> Any:
    """Extract the value shape exposed by generated panels and run_code."""
    if not isinstance(result, dict):
        return result

    candidate = result.get("result") or result.get("completed_result")
    if isinstance(candidate, dict):
        if candidate.get("success") is False:
            error = candidate.get("status_text") or candidate.get("statusText")
            return {"error": error if isinstance(error, str) and error else "Interaction failed"}

        payload = candidate.get("payload")
        if isinstance(payload, dict):
            if "data" in payload:
                return payload.get("data")
            return payload
        return None

    if result.get("outcome") == "operation_handle" and result.get("operation_handle"):
        return result.get("operation_handle")

    return result


async def _get_affordance(
    thing_id: str,
    affordance_type: str,
    affordance_name: str,
) -> dict[str, Any]:
    payload = await _run_with_session(
        lambda session: ThingCatalogQueryService(session).get_affordance(
            decode_thing_id(thing_id),
            affordance_type,
            affordance_name,
        )
    )
    return {
        "thing_id": thing_id,
        "name": payload.get("name", affordance_name),
        "type": affordance_type,
        "definition": payload.get("definition"),
    }


@tool
async def registry_health() -> dict[str, Any]:
    """Check registry health and return the REST base URL."""
    return {
        "status": "ok",
        "product": "wot_registry",
        "rest_base_url": get_registry_settings().REGISTRY_PUBLIC_URL,
    }


@tool
async def things_list(
    query: str = "",
    page: int = 1,
    per_page: int = 25,
    source: str = "",
) -> dict[str, Any]:
    """List stored Thing Descriptions from the registry catalog. Optionally
    filter by source (e.g. "manual" or "auto-discovered")."""
    normalized_page = _bounded_int(page, default=1, minimum=1, maximum=1_000_000)
    normalized_per_page = _bounded_int(per_page, default=25, minimum=1, maximum=200)
    normalized_source = source.strip() or None

    return await _run_with_session(
        lambda session: ThingCatalogQueryService(session).list_owned_things(
            query=query,
            page=normalized_page,
            per_page=normalized_per_page,
            source=normalized_source,
        )
    )


@tool
async def things_search(query: str, k: int = 5) -> dict[str, Any]:
    """Run semantic Thing search across the catalog."""
    normalized_query = query.strip()
    if not normalized_query:
        return {"error": "query must not be empty", "items": [], "query": normalized_query}
    normalized_k = _bounded_int(k, default=5, minimum=1, maximum=20)
    search_service = get_active_search_service()
    if search_service is None:
        return {"error": "Search service is not ready", "items": [], "query": normalized_query}

    items = await search_service.search(query=normalized_query, k=normalized_k)
    return {"items": items, "query": normalized_query, "k": normalized_k}


@tool
async def things_sparql(query: str, limit: int = 50) -> dict[str, Any]:
    """Run a read-only SPARQL query over the local Thing knowledge graph.

    Use this for structured questions about registered Things that semantic search
    cannot answer: joins across Things, type/unit filters, containment/topology hops,
    counts and aggregates. The graph is built from Thing Descriptions. Call
    describe_rdf_schema first if you are unsure which classes/predicates exist. Only
    SELECT, ASK, CONSTRUCT, or DESCRIBE are allowed; SERVICE/federation is not supported.
    """
    normalized_query = query.strip()
    if not normalized_query:
        return {"error": "query must not be empty", "query": normalized_query}
    normalized_limit = _bounded_int(limit, default=50, minimum=1, maximum=500)
    try:
        return await _rdf_client().query(query=normalized_query, limit=normalized_limit)
    except Exception as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "query": normalized_query,
            "limit": normalized_limit,
            "result": None,
        }


@tool
async def describe_rdf_schema(limit: int = 50) -> dict[str, Any]:
    """List the domain classes and predicates present in the local Thing knowledge graph.

    Call this before writing a things_sparql query when unsure which classes or predicates
    exist. Returns the real vocabulary in the graph with usage counts, plus a prefix map —
    excluding WoT Thing-Description plumbing (td:, wotsec:, hctl:, jsonschema:, and protocol
    bindings such as htv:), which describe TD mechanics rather than device/place semantics.
    """
    normalized_limit = _bounded_int(limit, default=50, minimum=1, maximum=200)
    client = _rdf_client()
    try:
        class_result = await client.query(query=CLASSES_QUERY, limit=500)
        predicate_result = await client.query(query=PREDICATES_QUERY, limit=500)
    except Exception as exc:
        return {"status": "failed", "error": str(exc), "classes": [], "predicates": []}
    return summarize_schema(
        class_rows=class_result.get("rows", []) if isinstance(class_result, dict) else [],
        predicate_rows=predicate_result.get("rows", [])
        if isinstance(predicate_result, dict)
        else [],
        limit=normalized_limit,
    )


@tool
async def things_get(thing_id: str) -> dict[str, Any]:
    """Fetch one stored Thing Description by id."""
    payload = await _run_with_session(
        lambda session: ThingCatalogQueryService(session).get_owned_thing(decode_thing_id(thing_id))
    )
    return _thing_summary(payload)


@tool
async def wot_get_property(thing_id: str, property_name: str) -> dict[str, Any]:
    """Get the raw property definition from a Thing Description."""
    return await _get_affordance(thing_id, "properties", property_name)


@tool
async def wot_get_action(thing_id: str, action_name: str) -> dict[str, Any]:
    """Get the raw action definition from a Thing Description."""
    return await _get_affordance(thing_id, "actions", action_name)


@tool
async def wot_get_event(thing_id: str, event_name: str) -> dict[str, Any]:
    """Get the raw event definition from a Thing Description."""
    return await _get_affordance(thing_id, "events", event_name)


@tool
def things_validate(document: dict[str, Any]) -> dict[str, Any]:
    """Validate a Thing Description without storing it."""
    sanitized = validate_document(document)
    return _thing_summary(
        {
            "id": sanitized.get("id"),
            "title": sanitized.get("title"),
            "description": sanitized.get("description", ""),
            "document": sanitized,
        }
    )


@tool
async def things_upsert(thing_id: str, document: dict[str, Any]) -> dict[str, Any]:
    """Create or update a Thing Description in the catalog."""
    if _looks_like_abstract_virtual_thing(document):
        return {
            "error": (
                "This looks like an abstract computed/emitted virtual Thing. "
                "Use create_virtual_thing plus add_virtual_* instead of things_upsert "
                "so wotbot can create bindings and virtual-servient can produce "
                "concrete HTTP forms."
            )
        }
    sanitized = validate_document(document)
    decoded_thing_id = decode_thing_id(thing_id)
    payload = await _run_with_session(
        lambda session: _thing_summary(
            serialize_thing(
                ThingCatalogWriteService(session).update(decoded_thing_id, sanitized),
                include_document=True,
            )
        )
    )
    return payload


def _looks_like_abstract_virtual_thing(document: dict[str, Any]) -> bool:
    for section in ("properties", "actions", "events"):
        affordances = document.get(section)
        if not isinstance(affordances, dict):
            continue
        for definition in affordances.values():
            if not isinstance(definition, dict):
                continue
            if definition.get("computed") is True or definition.get("emitted") is True:
                return True
            forms = definition.get("forms")
            if not isinstance(forms, list):
                continue
            for form in forms:
                if not isinstance(form, dict):
                    continue
                href = form.get("href")
                if isinstance(href, str) and href.startswith("urn:virtual"):
                    return True
    return False


@tool
async def things_delete(thing_id: str) -> dict[str, str]:
    """Delete a Thing Description by id."""
    decoded_thing_id = decode_thing_id(thing_id)
    await _run_with_session(
        lambda session: (
            ThingCatalogWriteService(session).delete(decoded_thing_id)
            or {"id": decoded_thing_id, "status": "deleted"}
        )
    )
    return {"id": decoded_thing_id, "status": "deleted"}


@tool
async def wot_get_runtime_health() -> dict[str, Any]:
    """Return the live runtime health from wot_runtime."""
    return await _runtime_client().get_runtime_health()


@tool
async def wot_read_property(
    thing_id: str,
    property_name: str,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
) -> Any:
    """Read a live WoT property and return the decoded property value directly."""
    return _decoded_runtime_value(
        await _runtime_client().read_property(
            thing_id=thing_id,
            property_name=property_name,
            uri_variables=uri_variables,
            form_index=form_index,
        )
    )


@tool
async def wot_write_property(
    thing_id: str,
    property_name: str,
    value: Any,
    value_content_type: str | None = None,
    value_base64: str | None = None,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
) -> Any:
    """Write a live WoT property and return the decoded response value directly."""
    return _decoded_runtime_value(
        await _runtime_client().write_property(
            thing_id=thing_id,
            property_name=property_name,
            value=value,
            value_content_type=value_content_type,
            value_base64=value_base64,
            uri_variables=uri_variables,
            form_index=form_index,
        )
    )


@tool
async def wot_invoke_action(
    thing_id: str,
    action_name: str,
    input: Any = None,
    input_content_type: str | None = None,
    input_base64: str | None = None,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
    idempotency_key: str | None = None,
) -> Any:
    """Invoke a live WoT action and return the decoded response value directly.

    IMPORTANT — authorization / bearer tokens: Do NOT pass tokens in the
    ``input`` field. The runtime automatically injects stored credentials
    (bearer tokens, API keys, etc.) from the credential store when it
    invokes the action. Tokens must be stored in advance via the
    credentials API (PUT /api/credentials/{thing_id}/{security_name})
    with the scheme and credential payload. Use things_get first to
    discover which security definitions the Thing requires, then store
    the matching credentials before invoking.
    """
    return _decoded_runtime_value(
        await _runtime_client().invoke_action(
            thing_id=thing_id,
            action_name=action_name,
            input=input,
            input_content_type=input_content_type,
            input_base64=input_base64,
            uri_variables=uri_variables,
            form_index=form_index,
            idempotency_key=idempotency_key,
        )
    )


@tool
async def wot_observe_property(
    thing_id: str,
    property_name: str,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
) -> dict[str, Any]:
    """Start or reuse a live WoT property observation."""
    return await _runtime_client().observe_property(
        thing_id=thing_id,
        property_name=property_name,
        uri_variables=uri_variables,
        form_index=form_index,
    )


@tool
async def wot_subscribe_event(
    thing_id: str,
    event_name: str,
    subscription_input: Any = None,
    subscription_input_content_type: str | None = None,
    subscription_input_base64: str | None = None,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
) -> dict[str, Any]:
    """Start or reuse a live WoT event subscription."""
    return await _runtime_client().subscribe_event(
        thing_id=thing_id,
        event_name=event_name,
        subscription_input=subscription_input,
        subscription_input_content_type=subscription_input_content_type,
        subscription_input_base64=subscription_input_base64,
        uri_variables=uri_variables,
        form_index=form_index,
    )


@tool
async def wot_remove_subscription(
    subscription_id: str,
    cancellation_input: Any = None,
    cancellation_input_content_type: str | None = None,
    cancellation_input_base64: str | None = None,
) -> dict[str, Any]:
    """Stop a live WoT observation or event subscription."""
    return await _runtime_client().remove_subscription(
        subscription_id=subscription_id,
        cancellation_input=cancellation_input,
        cancellation_input_content_type=cancellation_input_content_type,
        cancellation_input_base64=cancellation_input_base64,
    )


REGISTRY_TOOLS = [
    registry_health,
    things_list,
    things_search,
    things_sparql,
    describe_rdf_schema,
    things_get,
    wot_get_property,
    wot_get_action,
    wot_get_event,
    things_validate,
    things_upsert,
    things_delete,
    wot_get_runtime_health,
    wot_read_property,
    wot_write_property,
    wot_invoke_action,
    wot_observe_property,
    wot_subscribe_event,
    wot_remove_subscription,
]
