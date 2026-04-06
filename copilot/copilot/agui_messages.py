"""Utilities for normalizing AG-UI message payloads."""

from __future__ import annotations

from typing import Any


def strip_none_fields(value: Any) -> Any:
    """Recursively remove ``None`` values from AG-UI payload dicts.

    CopilotKit accepts omitted optional fields, but it rejects explicit
    ``null`` values for many message attributes when replaying history into a
    new run. Persisted LangGraph messages may include those ``null`` fields, so
    we normalize them before returning chat history to the frontend.
    """
    if isinstance(value, dict):
        return {
            key: strip_none_fields(item)
            for key, item in value.items()
            if item is not None
        }

    if isinstance(value, list):
        return [strip_none_fields(item) for item in value]

    return value
