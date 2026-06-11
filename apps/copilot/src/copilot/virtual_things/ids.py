from __future__ import annotations

import re
from uuid import uuid4

VIRTUAL_THING_PREFIX = "virtual:things:"


def is_virtual_thing_id(thing_id: str | None) -> bool:
    return isinstance(thing_id, str) and thing_id.startswith(VIRTUAL_THING_PREFIX)


def make_virtual_thing_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "virtual-thing"
    return f"{VIRTUAL_THING_PREFIX}{slug}-{uuid4().hex[:8]}"
