"""Helpers for creating the copilot LLM, MCP client, and loading tools."""

import asyncio
import logging
from datetime import timedelta

from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient

from copilot.models import Settings

logger = logging.getLogger(__name__)


def _make_mcp_client(settings: Settings) -> MultiServerMCPClient:
    connection: dict = {
        "transport": "streamable_http",
        "url": settings.wot_registry_url,
        "timeout": timedelta(seconds=settings.wot_registry_timeout_seconds),
        "sse_read_timeout": timedelta(seconds=settings.wot_registry_sse_read_timeout_seconds),
    }
    if settings.wot_registry_token:
        connection["headers"] = {"Authorization": f"Bearer {settings.wot_registry_token}"}
    return MultiServerMCPClient({"wot_registry": connection})


def _make_llm(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=120,
        max_retries=2,
    )


# Short, unambiguous descriptions for small models.
_TOOL_DESCRIPTION_OVERRIDES: dict[str, str] = {
    "things_list": "List devices in the catalog. Returns id and title.",
    "things_search": "Semantic search for devices. Returns id, title, and summary.",
    "things_get": "Fetch the full Thing Description (TD) for one device by id.",
    "things_validate": "Validate a Thing Description document.",
    "things_upsert": "Create or update a Thing Description.",
    "things_delete": "Delete a Thing Description by id.",
    "wot_get_action": "Get action schema: input/output types and uriVariables.",
    "wot_get_property": "Get property schema: data type and uriVariables.",
    "wot_get_event": "Get event schema: data type and subscription info.",
    "wot_get_runtime_health": "Check if the WoT runtime is healthy.",
    "wot_invoke_action": "Invoke a live device action. Pass input and uri_variables.",
    "wot_read_property": "Read a live property value from a device.",
    "wot_write_property": "Write a value to a live device property.",
    "wot_observe_property": "Start observing a live property for changes.",
    "wot_subscribe_event": "Subscribe to a live device event.",
    "wot_remove_subscription": "Stop an observation or event subscription.",
    "registry_health": "Check registry health.",
}


async def _load_mcp_tools(
    client: MultiServerMCPClient, retries: int = 5, delay: float = 3.0
) -> list:
    for attempt in range(1, retries + 1):
        try:
            tools = await client.get_tools()
            break
        except Exception:
            if attempt == retries:
                logger.exception("Failed to load MCP tools after %d attempts", retries)
                return []
            logger.warning(
                "MCP tools load attempt %d/%d failed, retrying in %.0fs…", attempt, retries, delay
            )
            await asyncio.sleep(delay)

    for tool in tools:
        tool.handle_tool_error = True
        if tool.name in _TOOL_DESCRIPTION_OVERRIDES:
            tool.description = _TOOL_DESCRIPTION_OVERRIDES[tool.name]

    return list(tools)
