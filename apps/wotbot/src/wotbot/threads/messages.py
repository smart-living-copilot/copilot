"""Checkpoint message conversion helpers for thread APIs."""

from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder

from wotbot.core.agui_messages import strip_none_fields


async def checkpoint_thread_messages(
    checkpointer: Any,
    thread_id: str,
) -> list[dict[str, Any]]:
    state = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
    if state is None or state.checkpoint is None:
        return []

    from ag_ui_langgraph.utils import langchain_messages_to_agui  # type: ignore[import-untyped]

    channel_values = state.checkpoint.get("channel_values", {})
    messages = channel_values.get("messages", [])
    if not isinstance(messages, list):
        return []

    agui_messages = jsonable_encoder(langchain_messages_to_agui(messages))
    return strip_none_fields(agui_messages)
