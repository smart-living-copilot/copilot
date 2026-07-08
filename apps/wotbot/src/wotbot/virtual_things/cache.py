from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from wotbot.virtual_things.schemas import json_safe

_CACHE: dict[str, tuple[float, Any]] = {}


@dataclass(frozen=True)
class CacheHit:
    found: bool
    value: Any = None


def get_cached_value(key: str) -> CacheHit:
    entry = _CACHE.get(key)
    if entry is None:
        return CacheHit(found=False)
    expires_at, value = entry
    if expires_at <= time.monotonic():
        _CACHE.pop(key, None)
        return CacheHit(found=False)
    return CacheHit(found=True, value=value)


def set_cached_value(key: str, value: Any, ttl_seconds: int) -> None:
    _CACHE[key] = (time.monotonic() + ttl_seconds, json_safe(value))
