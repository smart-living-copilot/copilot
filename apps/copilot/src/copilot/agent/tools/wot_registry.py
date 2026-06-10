"""LangGraph tools for the WoT registry and runtime."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from copilot.core.config import get_settings as get_registry_settings
from copilot.core.database import get_session_factory
from copilot.core.llm import make_llm
from copilot.search import get_active_search_service
from copilot.catalog import serialize_thing, validate_document
from copilot.catalog.ids import decode_thing_id
from copilot.catalog.service import ThingCatalogQueryService, ThingCatalogWriteService
from copilot.clients.rdf_service import RdfServiceClient, RdfServiceError
from copilot.clients.wot_runtime import WotRuntimeClient
from copilot.rdf.endpoint_context import load_endpoint_contexts


class EndpointSparqlDraft(BaseModel):
    query: str = Field(description="A complete read-only SPARQL query for one endpoint")
    rationale: str = Field(default="", description="Brief reason for the query shape")


_ENDPOINT_DRAFT_SYSTEM_PROMPT = """\
You draft SPARQL for one registered external SPARQL endpoint.

Rules:
- Use only read-only SPARQL: SELECT, ASK, CONSTRUCT, or DESCRIBE.
- Query only the provided endpoint vocabulary and examples.
- Prefer direct patterns against this endpoint. Use SERVICE only when the intent
  requires an open public SPARQL endpoint that this endpoint can query.
- Keep result size bounded and compatible with the requested limit.
- Include explicit PREFIX declarations for every prefixed name you use.
- Prefer endpoint example queries as few-shot patterns when available.
"""


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


def _load_knowledge_endpoint_context(endpoint_id: str) -> dict[str, Any]:
    session_factory = get_session_factory()
    with session_factory() as session:
        contexts = load_endpoint_contexts(session, [endpoint_id])
    return contexts[0]


async def _execute_sparql_query(
    *,
    query: str,
    endpoint_id: str,
    limit: int,
) -> dict[str, Any]:
    return await _rdf_client().query_endpoint(
        thing_id=endpoint_id,
        query=query,
        limit=limit,
    )


def _as_model_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _endpoint_draft_prompt(
    *,
    intent: str,
    endpoint_context: dict[str, Any],
    limit: int,
    attempts: list[dict[str, Any]],
) -> list[Any]:
    payload: dict[str, Any] = {
        "intent": intent,
        "limit": limit,
        "endpoint": endpoint_context,
    }
    if attempts:
        payload["repair"] = {
            "instruction": (
                "The previous SPARQL draft failed. Draft a corrected query and do not "
                "repeat the failed query unchanged."
            ),
            "previous_attempts": attempts,
        }
    return [
        SystemMessage(content=_ENDPOINT_DRAFT_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)),
    ]


async def _draft_endpoint_query(
    *,
    llm: Any,
    intent: str,
    endpoint_context: dict[str, Any],
    limit: int,
    attempts: list[dict[str, Any]],
) -> str:
    draft_llm = llm.with_structured_output(EndpointSparqlDraft)
    raw_draft = await draft_llm.ainvoke(
        _endpoint_draft_prompt(
            intent=intent,
            endpoint_context=endpoint_context,
            limit=limit,
            attempts=attempts,
        )
    )
    draft = _as_model_dict(raw_draft)
    query = str(draft.get("query") or "").strip()
    if not query:
        raise ValueError("SPARQL draft was empty")
    return query


def _attempt_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    results = result.get("results")
    if not isinstance(results, dict):
        return {"type": "unknown"}
    if isinstance(results.get("results"), dict):
        bindings = results["results"].get("bindings")
        return {
            "type": "select",
            "row_count": len(bindings) if isinstance(bindings, list) else 0,
        }
    if "boolean" in results:
        return {"type": "ask", "boolean": bool(results.get("boolean"))}
    return {"type": "json"}


def _can_redraft(error: Exception) -> bool:
    if isinstance(error, RdfServiceError):
        return bool(error.retryable)
    normalized = str(error).lower()
    return not any(
        marker in normalized
        for marker in ("401", "403", "unauthorized", "forbidden", "credential")
    )


async def _query_endpoint_knowledge(
    *,
    intent: str,
    endpoint_id: str,
    limit: int,
) -> dict[str, Any]:
    endpoint_context = await asyncio.to_thread(_load_knowledge_endpoint_context, endpoint_id)
    settings = get_registry_settings()
    llm = make_llm(settings)
    attempts: list[dict[str, Any]] = []
    last_error = ""
    query = ""

    for attempt_number in range(1, 3):
        try:
            query = await _draft_endpoint_query(
                llm=llm,
                intent=intent,
                endpoint_context=endpoint_context,
                limit=limit,
                attempts=attempts,
            )
        except Exception as exc:
            last_error = f"SPARQL draft failed: {exc}"
            break

        try:
            result = await _execute_sparql_query(
                query=query,
                endpoint_id=endpoint_id,
                limit=limit,
            )
        except Exception as exc:
            last_error = str(exc)
            category = getattr(exc, "category", "")
            attempts.append(
                {
                    "attempt": attempt_number,
                    "query": query,
                    "status": "error",
                    "error": last_error,
                    "error_category": category if isinstance(category, str) else "",
                }
            )
            if attempt_number >= 2 or not _can_redraft(exc):
                break
            continue

        attempts.append(
            {
                "attempt": attempt_number,
                "query": query,
                "status": "ok",
                "result": _attempt_result_summary(result),
            }
        )
        return {
            "status": "ok",
            "intent": intent,
            "endpoint_id": endpoint_id,
            "endpoint": endpoint_context,
            "query": query,
            "limit": limit,
            "attempts": attempts,
            "summary": "SPARQL endpoint query completed.",
            "result": result,
        }

    return {
        "status": "failed",
        "error": last_error,
        "intent": intent,
        "endpoint_id": endpoint_id,
        "endpoint": endpoint_context,
        "query": query,
        "limit": limit,
        "attempts": attempts,
        "summary": f"SPARQL endpoint query failed: {last_error}",
        "result": None,
    }


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
) -> dict[str, Any]:
    """List stored Thing Descriptions from the registry catalog."""
    normalized_page = _bounded_int(page, default=1, minimum=1, maximum=1_000_000)
    normalized_per_page = _bounded_int(per_page, default=25, minimum=1, maximum=200)

    return await _run_with_session(
        lambda session: ThingCatalogQueryService(session).list_owned_things(
            query=query,
            page=normalized_page,
            per_page=normalized_per_page,
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
async def query_knowledge(
    intent: str,
    endpoint_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Answer a structured knowledge intent against one registered SPARQL endpoint Thing.

    Use this when the user asks for facts from an external knowledge graph. Pass a
    natural-language intent plus the endpoint Thing id; the tool drafts one read-only
    SPARQL query for that endpoint and retries once on endpoint/query errors.
    """
    normalized_intent = intent.strip()
    if not normalized_intent:
        return {"error": "intent must not be empty", "intent": normalized_intent}
    normalized_endpoint_id = endpoint_id.strip()
    if not normalized_endpoint_id:
        return {
            "error": "endpoint_id must not be empty",
            "intent": normalized_intent,
            "endpoint_id": normalized_endpoint_id,
        }
    normalized_limit = _bounded_int(limit, default=50, minimum=1, maximum=500)
    try:
        return await _query_endpoint_knowledge(
            intent=normalized_intent,
            endpoint_id=normalized_endpoint_id,
            limit=normalized_limit,
        )
    except Exception as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "intent": normalized_intent,
            "endpoint_id": normalized_endpoint_id,
            "query": "",
            "limit": normalized_limit,
            "attempts": [],
            "summary": f"SPARQL endpoint query failed: {exc}",
            "result": None,
        }


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
    """Invoke a live WoT action and return the decoded response value directly."""
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
    query_knowledge,
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
