"""Checkpoint state helpers for thread APIs."""

from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder


async def checkpoint_thread_state(
    checkpointer: Any,
    thread_id: str,
) -> dict[str, Any]:
    """Return a thread's checkpoint state in LangGraph's own shape.

    Feeds ``useStream``'s ``initialValues``. A custom ``transport`` has no
    ``fetchStateHistory`` option, so the app seeds history itself and this is
    where it comes from.

    """
    state = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
    if state is None or state.checkpoint is None:
        return {"values": {"messages": []}}

    channel_values = state.checkpoint.get("channel_values", {})
    messages = channel_values.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    return {"values": {**channel_values, "messages": jsonable_encoder(messages)}}
