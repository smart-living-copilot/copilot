"""LangGraph tools for the WoT registry and runtime."""

from typing import Any
from urllib.parse import quote

import httpx
from langchain_core.tools import tool

from copilot.core.settings import Settings
from copilot.things import validate_document


def _settings() -> Settings:
    return Settings()


def _registry_base_url(settings: Settings) -> str:
    url = settings.wot_registry_url.rstrip("/")
    if url.endswith("/mcp"):
        url = url[: -len("/mcp")]
    if url.endswith("/api"):
        url = url[: -len("/api")]
    return url


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _path_segment(value: str) -> str:
    return quote(value, safe="")


def _response_error(response: httpx.Response) -> ValueError:
    detail: Any = None
    try:
        data = response.json()
    except ValueError:
        data = None

    if isinstance(data, dict):
        detail = data.get("detail")
    if isinstance(detail, str) and detail.strip():
        return ValueError(detail)
    return ValueError(f"Request failed with status {response.status_code}")


async def _request_registry(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = _settings()
    async with httpx.AsyncClient(timeout=settings.wot_registry_timeout_seconds) as client:
        response = await client.request(
            method,
            f"{_registry_base_url(settings)}{path}",
            headers=_auth_headers(settings.wot_registry_token),
            json=json,
            params=params,
        )

    if response.status_code >= 400:
        raise _response_error(response)

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Registry returned a non-object response")
    return data


async def _request_runtime(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = _settings()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.request(
            method,
            f"{settings.wot_runtime_url.rstrip('/')}{path}",
            headers=_auth_headers(settings.wot_runtime_api_token),
            json=json,
        )

    if response.status_code >= 400:
        raise _response_error(response)

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("WoT runtime returned a non-object response")
    return data


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


async def _get_affordance(
    thing_id: str,
    affordance_type: str,
    affordance_name: str,
) -> dict[str, Any]:
    path = (
        f"/api/things/{_path_segment(thing_id)}/{affordance_type}/"
        f"{_path_segment(affordance_name)}"
    )
    payload = await _request_registry("GET", path)
    return {
        "thing_id": thing_id,
        "name": payload.get("name", affordance_name),
        "type": affordance_type,
        "definition": payload.get("definition"),
    }


@tool
async def registry_health() -> dict[str, Any]:
    """Check registry health and return the REST base URL."""
    settings = _settings()
    payload = await _request_registry("GET", "/health")
    return {
        **payload,
        "product": "wot_registry",
        "rest_base_url": _registry_base_url(settings),
    }


@tool
async def things_list(
    query: str = "",
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any]:
    """List stored Thing Descriptions from the registry catalog."""
    return await _request_registry(
        "GET",
        "/api/things",
        params={"q": query, "page": page, "per_page": per_page},
    )


@tool
async def things_search(query: str, k: int = 5) -> dict[str, Any]:
    """Run semantic Thing search across the catalog."""
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty")
    if k < 1 or k > 20:
        raise ValueError("k must be between 1 and 20")
    return await _request_registry(
        "GET",
        "/api/things/search",
        params={"q": normalized_query, "k": k},
    )


@tool
async def things_get(thing_id: str) -> dict[str, Any]:
    """Fetch one stored Thing Description by id."""
    payload = await _request_registry("GET", f"/api/things/{_path_segment(thing_id)}")
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
    payload = await _request_registry(
        "PUT",
        f"/api/things/{_path_segment(thing_id)}",
        json=sanitized,
    )
    return _thing_summary(payload)


@tool
async def things_delete(thing_id: str) -> dict[str, str]:
    """Delete a Thing Description by id."""
    payload = await _request_registry("DELETE", f"/api/things/{_path_segment(thing_id)}")
    return {
        "id": str(payload.get("id", thing_id)),
        "status": str(payload.get("status", "deleted")),
    }


@tool
async def wot_get_runtime_health() -> dict[str, Any]:
    """Return the live runtime health from wot_runtime."""
    return await _request_runtime("GET", "/health")


@tool
async def wot_read_property(
    thing_id: str,
    property_name: str,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
) -> dict[str, Any]:
    """Read a live WoT property through wot_runtime."""
    return await _request_runtime(
        "POST",
        "/runtime/read-property",
        json={
            "thing_id": thing_id,
            "property_name": property_name,
            "uri_variables": uri_variables or {},
            "form_index": form_index,
        },
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
) -> dict[str, Any]:
    """Write a live WoT property through wot_runtime."""
    return await _request_runtime(
        "POST",
        "/runtime/write-property",
        json={
            "thing_id": thing_id,
            "property_name": property_name,
            "value": value,
            "value_content_type": value_content_type,
            "value_base64": value_base64,
            "uri_variables": uri_variables or {},
            "form_index": form_index,
        },
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
) -> dict[str, Any]:
    """Invoke a live WoT action through wot_runtime."""
    return await _request_runtime(
        "POST",
        "/runtime/invoke-action",
        json={
            "thing_id": thing_id,
            "action_name": action_name,
            "input": input,
            "input_content_type": input_content_type,
            "input_base64": input_base64,
            "uri_variables": uri_variables or {},
            "form_index": form_index,
            "idempotency_key": idempotency_key,
        },
    )


@tool
async def wot_observe_property(
    thing_id: str,
    property_name: str,
    uri_variables: dict[str, Any] | None = None,
    form_index: int | None = None,
) -> dict[str, Any]:
    """Start or reuse a live WoT property observation."""
    return await _request_runtime(
        "POST",
        "/runtime/observe-property",
        json={
            "thing_id": thing_id,
            "property_name": property_name,
            "uri_variables": uri_variables or {},
            "form_index": form_index,
        },
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
    return await _request_runtime(
        "POST",
        "/runtime/subscribe-event",
        json={
            "thing_id": thing_id,
            "event_name": event_name,
            "subscription_input": subscription_input,
            "subscription_input_content_type": subscription_input_content_type,
            "subscription_input_base64": subscription_input_base64,
            "uri_variables": uri_variables or {},
            "form_index": form_index,
        },
    )


@tool
async def wot_remove_subscription(
    subscription_id: str,
    cancellation_input: Any = None,
    cancellation_input_content_type: str | None = None,
    cancellation_input_base64: str | None = None,
) -> dict[str, Any]:
    """Stop a live WoT observation or event subscription."""
    return await _request_runtime(
        "POST",
        "/runtime/remove-subscription",
        json={
            "subscription_id": subscription_id,
            "cancellation_input": cancellation_input,
            "cancellation_input_content_type": cancellation_input_content_type,
            "cancellation_input_base64": cancellation_input_base64,
        },
    )


REGISTRY_TOOLS = [
    registry_health,
    things_list,
    things_search,
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
