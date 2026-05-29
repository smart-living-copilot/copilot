"""Helpers for deriving sidebar-friendly thread titles from chat messages."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

MAX_THREAD_TITLE_LENGTH = 50


def _message_field(message: Any, field: str) -> Any:
    if isinstance(message, dict):
        return message.get(field)
    return getattr(message, field, None)


def _is_user_message(message: Any) -> bool:
    role = _message_field(message, "role")
    if isinstance(role, str):
        return role == "user"

    message_type = _message_field(message, "type")
    return isinstance(message_type, str) and message_type in {"human", "user"}


def _flatten_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, dict):
        block_type = content.get("type")
        text = content.get("text")
        if block_type in {"text", "input_text"} and isinstance(text, str):
            return text.strip()
        return ""

    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text = item.strip()
            if text:
                parts.append(text)
            continue

        if not isinstance(item, dict):
            continue

        block_type = item.get("type")
        text = item.get("text")
        if block_type in {"text", "input_text"} and isinstance(text, str):
            stripped = text.strip()
            if stripped:
                parts.append(stripped)

    return " ".join(parts).strip()


def suggest_thread_title(
    messages: Sequence[Any],
    *,
    max_length: int = MAX_THREAD_TITLE_LENGTH,
) -> str | None:
    """Return a short title derived from the latest user-authored message."""
    for message in reversed(messages):
        if not _is_user_message(message):
            continue

        content = _flatten_text_content(_message_field(message, "content"))
        if content:
            return content[:max_length]

    return None
