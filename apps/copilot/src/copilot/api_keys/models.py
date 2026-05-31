from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ApiKeyRecord:
    id: str
    key_prefix: str
    name: str
    scopes: list[str]
    user_id: str
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool = True


@dataclass(frozen=True)
class ApiKeyRow:
    id: str
    key_prefix: str
    key_hash: str
    name: str
    scopes: list[str]
    user_id: str
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool = True
