from __future__ import annotations

from langchain_core.runnables import RunnableConfig


def thread_id_from_config(config: RunnableConfig | None) -> str | None:
    value = (config or {}).get("configurable", {}).get("thread_id")
    return value if isinstance(value, str) and value else None


__all__ = ["thread_id_from_config"]
