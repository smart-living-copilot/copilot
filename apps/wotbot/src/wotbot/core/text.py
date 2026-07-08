from __future__ import annotations


def truncate_text(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."


__all__ = ["truncate_text"]
