"""Helpers for voice-safe assistant output."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk

VOICE_STREAM_NODES = frozenset({"respond", "control_llm", "analysis_llm"})


def text_from_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    text_parts = []
    for item in content:
        if isinstance(item, str):
            text_parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            text_parts.append(item["text"])
    return "".join(text_parts)


def assistant_text_from_graph_result(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    messages = result.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        return text_from_message_content(message.content).strip()
    return ""


def voice_stream_text_from_event(event: Any) -> str:
    if not isinstance(event, tuple) or len(event) != 2:
        return ""
    message, metadata = event
    if not isinstance(message, AIMessageChunk) or not isinstance(metadata, dict):
        return ""
    if metadata.get("langgraph_node") not in VOICE_STREAM_NODES:
        return ""
    if getattr(message, "tool_call_chunks", None):
        return ""
    return text_from_message_content(message.content)


def is_voice_stream_event(event: Any) -> bool:
    return bool(voice_stream_text_from_event(event))
