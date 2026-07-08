"""LangChain tool for executing Python code in an isolated session."""

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from wotbot.clients.code_executor import (
    CodeExecutorClient,
    format_code_execution_result,
)
from wotbot.core.settings import Settings

_settings = Settings()
_code_executor_client = CodeExecutorClient(_settings)


@tool
async def run_code(code: str, config: RunnableConfig) -> dict:
    """Execute Python code in an isolated Python session.

    The session persists for the duration of the chat, so variables
    and imports carry over between calls. Common libraries available:
    pandas, matplotlib, plotly, numpy, json, math, datetime.

    Use this tool when the user asks you to analyse data, compute something,
    or create a plot/chart. Return the structured tool output directly.
    The frontend renders code artifacts below the tool call, so refer to
    them naturally in your final answer and never mention raw filenames.
    """
    chat_id = config.get("configurable", {}).get("thread_id", "default")
    try:
        response = await _code_executor_client.execute(session_id=chat_id, code=code)
        return format_code_execution_result(response)
    except httpx.ConnectError:
        return {"error": "Code executor service is unavailable. Please try again later."}
    except httpx.TimeoutException:
        return {
            "error": (
                f"Code executor request timed out after "
                f"{_settings.code_executor_timeout_seconds} seconds."
            )
        }
    except httpx.HTTPStatusError as e:
        detail = None
        try:
            detail = e.response.json().get("detail")
        except Exception:
            detail = None
        if detail:
            return {"error": detail}
        return {"error": f"Code execution failed with status {e.response.status_code}."}
