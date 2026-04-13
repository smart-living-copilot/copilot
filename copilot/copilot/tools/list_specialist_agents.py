"""LangChain tool that lists specialist agents from specialist-agent runtime."""

import httpx
from langchain_core.tools import tool

from copilot.models import Settings

_settings = Settings()


@tool
async def list_specialist_agents(query: str = "agent") -> dict:
    """List available specialist agents that match a query.

    Always call this before selecting a specialist agent for delegation.
    """

    headers = (
        {"Authorization": f"Bearer {_settings.internal_api_key}"}
        if _settings.internal_api_key
        else {}
    )

    search_query = (query or "agent").strip() or "agent"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_settings.specialist_agent_url}/agents/search",
                params={"q": search_query},
                headers=headers,
                timeout=float(_settings.specialist_agent_timeout_seconds),
            )
            response.raise_for_status()
            items = response.json()
    except httpx.ConnectError:
        return {"error": "Specialist agent runtime is unavailable."}
    except httpx.TimeoutException:
        return {
            "error": (
                "Specialist agent runtime timed out after "
                f"{_settings.specialist_agent_timeout_seconds} seconds."
            )
        }
    except httpx.HTTPStatusError as exc:
        detail = None
        try:
            detail = exc.response.json().get("detail")
        except Exception:
            detail = None
        return {"error": detail or f"Specialist listing failed ({exc.response.status_code})."}

    if not isinstance(items, list):
        return {"items": []}

    return {
        "count": len(items),
        "items": [
            {
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "tags": item.get("tags", []),
                "score": item.get("score", 0),
            }
            for item in items
            if isinstance(item, dict)
        ],
    }
