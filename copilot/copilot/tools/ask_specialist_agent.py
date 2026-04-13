"""LangChain tool that asks one specific specialist agent by id."""

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from copilot.models import Settings

_settings = Settings()


@tool
async def ask_specialist_agent(agent_id: str, query: str, config: RunnableConfig) -> dict:
    """Ask a specific specialist agent by id.

    Use after list_specialist_agents has identified candidate agents.
    """

    thread_id = config.get("configurable", {}).get("thread_id")
    headers = (
        {"Authorization": f"Bearer {_settings.internal_api_key}"}
        if _settings.internal_api_key
        else {}
    )

    payload = {
        "query": query,
        "thread_id": thread_id,
        "preferred_agent_id": agent_id,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_settings.specialist_agent_url}/agents/execute",
                json=payload,
                headers=headers,
                timeout=float(_settings.specialist_agent_timeout_seconds),
            )
            response.raise_for_status()
            data = response.json()
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
        return {"error": detail or f"Specialist execution failed ({exc.response.status_code})."}

    return {
        "agent": {
            "id": data.get("agent_id", ""),
            "title": data.get("agent_title", ""),
            "score": data.get("score", 0),
            "tool_calls": data.get("tool_calls", 0),
        },
        "answer": data.get("answer", ""),
    }
