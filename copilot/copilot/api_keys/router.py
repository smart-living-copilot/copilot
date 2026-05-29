from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from copilot.auth import User, require_scopes
from copilot.api_dependencies import SessionDep
from copilot.api_keys.service import ApiKeyManagementService


router = APIRouter(prefix="/api", tags=["api-keys"])


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(..., min_length=1)
    expires_at: Optional[datetime] = None


class ApiKeyResponse(BaseModel):
    id: str
    key_prefix: str
    name: str
    scopes: list[str]
    user_id: str
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool


class CreateApiKeyResponse(BaseModel):
    key: ApiKeyResponse
    raw_key: str


def _serialize_api_key(record) -> dict[str, Any]:
    return {
        "id": record.id,
        "key_prefix": record.key_prefix,
        "name": record.name,
        "scopes": record.scopes,
        "user_id": record.user_id,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "last_used_at": record.last_used_at.isoformat()
        if record.last_used_at
        else None,
        "is_active": record.is_active,
    }


@router.post("/keys", status_code=201)
def create_key(
    body: CreateApiKeyRequest,
    session: SessionDep,
    user: User = Depends(require_scopes(["keys:manage"])),
) -> dict[str, Any]:
    record, raw_key = ApiKeyManagementService(session).create_for_user(
        user=user,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )

    return {
        "key": _serialize_api_key(record),
        "raw_key": raw_key,
    }


@router.get("/keys")
def list_keys(
    session: SessionDep,
    user: User = Depends(require_scopes(["keys:manage"])),
) -> dict[str, Any]:
    records = ApiKeyManagementService(session).list_for_user(user.user_id)
    return {"items": [_serialize_api_key(record) for record in records]}


@router.delete("/keys/{key_id}")
def revoke_key(
    key_id: str,
    session: SessionDep,
    user: User = Depends(require_scopes(["keys:manage"])),
) -> dict[str, str]:
    ApiKeyManagementService(session).revoke_for_user(key_id, user.user_id)
    return {"id": key_id, "status": "revoked"}
