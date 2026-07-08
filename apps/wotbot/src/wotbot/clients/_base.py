from __future__ import annotations

from typing import Any


def setting_value(settings: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(settings, name):
            return getattr(settings, name)
    return default


__all__ = ["setting_value"]
