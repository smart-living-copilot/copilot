from __future__ import annotations

from typing import Any


def setting_value(settings: Any, *names: str, default: Any = None) -> Any:
    """Read the first present attribute from a settings object, supporting alias names."""
    for name in names:
        if hasattr(settings, name):
            return getattr(settings, name)
    return default
