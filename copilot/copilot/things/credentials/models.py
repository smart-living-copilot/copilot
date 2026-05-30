from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CredentialRow:
    id: str
    thing_id: str
    security_name: str
    scheme: str
    credentials: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None
