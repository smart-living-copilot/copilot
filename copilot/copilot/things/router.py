from typing import Any

from fastapi import APIRouter, Body, Depends, Query

from copilot.auth import User, require_scopes
from copilot.core.api_dependencies import DatabaseDep
from copilot.things.ids import decode_thing_id
from copilot.things.service import (
    ThingCatalogQueryService,
    ThingCatalogWriteService,
)
from copilot.things import serialize_thing, validate_document
from copilot.things.credentials.router import router as credentials_router

router = APIRouter(prefix="/api", tags=["things"])


# --- Affordance endpoints (must be registered before the catch-all {thing_id:path}) ---


@router.get("/things/{thing_id}/properties")
def list_thing_properties(
    thing_id: str,
    connection: DatabaseDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(connection).list_affordances(
        decode_thing_id(thing_id),
        "properties",
    )


@router.get("/things/{thing_id}/properties/{name}")
def get_thing_property(
    thing_id: str,
    name: str,
    connection: DatabaseDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(connection).get_affordance(
        decode_thing_id(thing_id),
        "properties",
        name,
    )


@router.get("/things/{thing_id}/actions")
def list_thing_actions(
    thing_id: str,
    connection: DatabaseDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(connection).list_affordances(
        decode_thing_id(thing_id),
        "actions",
    )


@router.get("/things/{thing_id}/actions/{name}")
def get_thing_action(
    thing_id: str,
    name: str,
    connection: DatabaseDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(connection).get_affordance(
        decode_thing_id(thing_id),
        "actions",
        name,
    )


@router.get("/things/{thing_id}/events")
def list_thing_events(
    thing_id: str,
    connection: DatabaseDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(connection).list_affordances(
        decode_thing_id(thing_id),
        "events",
    )


@router.get("/things/{thing_id}/events/{name}")
def get_thing_event(
    thing_id: str,
    name: str,
    connection: DatabaseDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(connection).get_affordance(
        decode_thing_id(thing_id),
        "events",
        name,
    )


# --- CRUD endpoints ---


@router.get("/things")
def list_owned_things(
    connection: DatabaseDep,
    q: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=200),
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(connection).list_owned_things(
        query=q,
        page=page,
        per_page=per_page,
    )


@router.get("/things/{thing_id:path}")
def get_owned_thing(
    thing_id: str,
    connection: DatabaseDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(connection).get_owned_thing(decode_thing_id(thing_id))


@router.post("/things", status_code=201)
def create_owned_thing(
    connection: DatabaseDep,
    document: dict[str, Any] = Body(...),
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    sanitized = validate_document(document)
    record = ThingCatalogWriteService(connection).create(sanitized)
    return serialize_thing(record, include_document=True)


@router.put("/things/{thing_id:path}")
def update_owned_thing(
    thing_id: str,
    connection: DatabaseDep,
    document: dict[str, Any] = Body(...),
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    sanitized = validate_document(document)
    decoded_thing_id = decode_thing_id(thing_id)
    record = ThingCatalogWriteService(connection).update(decoded_thing_id, sanitized)
    return serialize_thing(record, include_document=True)


@router.delete("/things/{thing_id:path}")
def delete_owned_thing(
    thing_id: str,
    connection: DatabaseDep,
    _user: User = Depends(require_scopes(["things:delete"])),
) -> dict[str, str]:
    decoded_thing_id = decode_thing_id(thing_id)
    ThingCatalogWriteService(connection).delete(decoded_thing_id)
    return {"id": decoded_thing_id, "status": "deleted"}


router.include_router(credentials_router)
