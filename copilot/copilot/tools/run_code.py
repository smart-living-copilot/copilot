"""LangChain tool for executing Python code in an isolated session."""

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from copilot.models import Settings

_settings = Settings()


def _build_artifacts(images: list[str], plotly: list[str]) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []

    for index, filename in enumerate(images, start=1):
        artifacts.append(
            {
                "ref": f"image_{index}",
                "kind": "image",
                "filename": filename,
            }
        )

    for index, filename in enumerate(plotly, start=1):
        artifacts.append(
            {
                "ref": f"chart_{index}",
                "kind": "plotly",
                "filename": filename,
            }
        )

    return artifacts


def _format_run_code_result(data: dict) -> dict:
    stdout = data.get("stdout", "").rstrip()
    artifacts = _build_artifacts(data.get("images", []), data.get("plotly", []))
    wot_calls = data.get("wot_calls", [])

    result: dict[str, object] = {}
    if stdout:
        result["stdout"] = stdout
    if artifacts:
        result["artifacts"] = artifacts
    if wot_calls:
        result["wot_calls"] = wot_calls
    if not result:
        result["stdout"] = "(no output)"

    return result


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
        headers = (
            {"Authorization": f"Bearer {_settings.internal_api_key}"}
            if _settings.internal_api_key
            else {}
        )
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_settings.code_executor_url}/execute",
                json={"session_id": chat_id, "code": code},
                headers=headers,
                timeout=float(_settings.code_executor_timeout_seconds),
            )
            resp.raise_for_status()
            return _format_run_code_result(resp.json())
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
