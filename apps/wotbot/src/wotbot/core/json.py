from __future__ import annotations

import json
from typing import Any


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True, default=str))


__all__ = ["json_safe"]
