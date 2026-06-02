from __future__ import annotations

import json
from typing import Any


def submitted_record_event_message(payload: Any) -> str:
    summary = submitted_record_summary(payload)
    if summary:
        return f"Structured record submitted: {summary}"
    return "Structured record submitted."


def submitted_record_summary(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data")
    if not isinstance(data, dict):
        return ""

    parts: list[str] = []
    for key, value in data.items():
        if len(parts) >= 5:
            parts.append("...")
            break
        value_text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True)
        parts.append(f"{key}={_truncate_text(str(value_text), max_length=80)}")

    return _truncate_text(", ".join(parts), max_length=320)


def _truncate_text(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."
