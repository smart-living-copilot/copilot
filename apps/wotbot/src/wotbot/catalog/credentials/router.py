from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from wotbot.auth import User, require_scopes, require_service
from wotbot.catalog.credentials.service import CredentialService
from wotbot.catalog.ids import decode_thing_id
from wotbot.core.api_dependencies import SessionDep

router = APIRouter(tags=["thing credentials"])


class SetCredentialBody(BaseModel):
    scheme: str
    credentials: dict[str, Any]


@router.put("/credentials/{thing_id:path}/{security_name}")
def upsert_credential(
    thing_id: str,
    security_name: str,
    session: SessionDep,
    body: SetCredentialBody = Body(...),
    _user: User = Depends(require_scopes(["credentials:write"])),
) -> dict[str, str]:
    decoded_id = decode_thing_id(thing_id)
    CredentialService(session).upsert(
        thing_id=decoded_id,
        security_name=security_name,
        scheme=body.scheme,
        credentials=body.credentials,
    )
    return {"status": "ok"}


@router.get("/credentials/{thing_id:path}")
def list_thing_credentials(
    thing_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["credentials:read"])),
) -> dict[str, Any]:
    decoded_id = decode_thing_id(thing_id)
    items = CredentialService(session).list_for_thing(decoded_id)
    return {"items": items}


@router.delete("/credentials/{thing_id:path}/{security_name}")
def remove_credential(
    thing_id: str,
    security_name: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["credentials:write"])),
) -> dict[str, str]:
    decoded_id = decode_thing_id(thing_id)
    CredentialService(session).delete(
        thing_id=decoded_id,
        security_name=security_name,
    )
    return {"status": "deleted"}


@router.get("/runtime/secrets")
def fetch_runtime_secrets(
    session: SessionDep,
    _user: User = Depends(require_service(["wot_runtime"])),
) -> dict[str, Any]:
    return CredentialService(session).get_runtime_secrets()
