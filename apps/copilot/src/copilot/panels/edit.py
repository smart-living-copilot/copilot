"""LLM-assisted editing of a pinned panel.

Runs a focused turn of the foreground agent graph, seeded with the panel's
current HTML + capabilities and the user's natural-language instruction, and
extracts the updated panel from the agent's ``create_web_interface`` call. The
agent can discover new devices (things_search / wot_get_*) when the edit needs
an affordance the panel doesn't already use, and it re-declares the capability
allowlist for the new version.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

_EDIT_INSTRUCTIONS = """\
You are updating an existing smart-home control panel (an interactive HTML/JS
mini-interface). Apply the requested change, then emit the COMPLETE updated panel
using the create_web_interface tool — re-declaring every capability the updated
panel uses. Make the smallest change that satisfies the request and keep the rest
of the panel intact. If the change needs a device or affordance the panel does not
already use, discover it first (things_search, wot_get_property, wot_get_action).
Panel JavaScript must treat window.wot.readProperty/writeProperty/invokeAction
results as decoded device values directly. Do not access transport wrapper
fields like result, payload, completed_result, or payload.data unless those
fields are explicitly part of the inspected device value schema.

Requested change:
{instruction}

Current capabilities (JSON):
{capabilities}

Current panel HTML:
{html}
"""


def _extract_updated_panel(
    messages: list[Any],
) -> tuple[str, list[dict[str, Any]]] | None:
    """Pull the latest create_web_interface html (args) + capabilities (result)."""
    calls_by_id: dict[str, dict[str, Any]] = {}
    for message in messages:
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls:
                if tool_call.get("name") == "create_web_interface":
                    call_id = tool_call.get("id")
                    if isinstance(call_id, str):
                        calls_by_id[call_id] = tool_call

    result: tuple[str, list[dict[str, Any]]] | None = None
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        tool_call = calls_by_id.get(message.tool_call_id)
        if not tool_call:
            continue
        html = (tool_call.get("args") or {}).get("html")
        if not isinstance(html, str) or not html:
            continue
        content = message.content
        parsed = json.loads(content) if isinstance(content, str) else content
        artifacts = parsed.get("artifacts") if isinstance(parsed, dict) else None
        if not isinstance(artifacts, list) or not artifacts:
            continue
        capabilities = artifacts[0].get("capabilities")
        result = (html, capabilities if isinstance(capabilities, list) else [])

    return result


async def run_panel_edit(
    *,
    graph: Any,
    checkpointer: Any,
    html: str,
    capabilities: list[dict[str, Any]],
    instruction: str,
) -> tuple[str, list[dict[str, Any]]] | None:
    """Run one agent turn to edit the panel; returns (new_html, capabilities)."""
    prompt = _EDIT_INSTRUCTIONS.format(
        instruction=instruction.strip(),
        capabilities=json.dumps(capabilities, ensure_ascii=True),
        html=html,
    )
    thread_id = f"panel-edit-{uuid.uuid4().hex}"
    try:
        state = await graph.ainvoke(
            {"messages": [HumanMessage(content=prompt)]},
            config={"configurable": {"thread_id": thread_id}},
        )
    finally:
        # Edit threads are throwaway; don't leave checkpoints lying around.
        if checkpointer is not None:
            try:
                await checkpointer.adelete_thread(thread_id)
            except Exception:
                pass

    messages = state.get("messages", []) if isinstance(state, dict) else []
    return _extract_updated_panel(messages)
