from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from copilot.auth import User, require_scopes
from copilot.core.api_dependencies import SessionDep
from copilot.core.llm import make_llm
from copilot.core.settings import Settings
from copilot.catalog.ids import decode_thing_id
from copilot.catalog.service import (
    ThingCatalogQueryService,
    ThingCatalogWriteService,
)
from copilot.catalog import serialize_thing, validate_document
from copilot.catalog.credentials.router import router as credentials_router
from copilot.catalog.enrichment import (
    EnrichmentError,
    enrich_thing_document,
    load_enrichment_config,
)

router = APIRouter(prefix="/api", tags=["things"])


@router.get("/things/{thing_id}/properties")
def list_thing_properties(
    thing_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).list_affordances(
        decode_thing_id(thing_id),
        "properties",
    )


@router.get("/things/{thing_id}/properties/{name}")
def get_thing_property(
    thing_id: str,
    name: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).get_affordance(
        decode_thing_id(thing_id),
        "properties",
        name,
    )


@router.get("/things/{thing_id}/actions")
def list_thing_actions(
    thing_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).list_affordances(
        decode_thing_id(thing_id),
        "actions",
    )


@router.get("/things/{thing_id}/actions/{name}")
def get_thing_action(
    thing_id: str,
    name: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).get_affordance(
        decode_thing_id(thing_id),
        "actions",
        name,
    )


@router.get("/things/{thing_id}/events")
def list_thing_events(
    thing_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).list_affordances(
        decode_thing_id(thing_id),
        "events",
    )


@router.get("/things/{thing_id}/events/{name}")
def get_thing_event(
    thing_id: str,
    name: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).get_affordance(
        decode_thing_id(thing_id),
        "events",
        name,
    )


@router.get("/things")
def list_owned_things(
    session: SessionDep,
    q: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=200),
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).list_owned_things(
        query=q,
        page=page,
        per_page=per_page,
    )


@router.post("/things/{thing_id:path}/enrich")
async def enrich_owned_thing(
    thing_id: str,
    request: Request,
    body: dict[str, Any] = Body(...),
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    document = body.get("document")
    if not isinstance(document, dict):
        raise HTTPException(status_code=422, detail="Body must include a document object")

    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        settings = Settings()

    config = load_enrichment_config(settings.thing_enrichment_config_path)
    llm = make_llm(settings)
    try:
        result = await enrich_thing_document(
            document,
            config=config,
            llm=llm,
            max_repair_attempts=settings.thing_enrichment_max_repair_attempts,
        )
    except EnrichmentError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.errors},
        ) from exc

    return result.model_dump()


@router.get("/things/{thing_id:path}")
def get_owned_thing(
    thing_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return ThingCatalogQueryService(session).get_owned_thing(decode_thing_id(thing_id))


@router.post("/things", status_code=201)
def create_owned_thing(
    session: SessionDep,
    document: dict[str, Any] = Body(...),
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    sanitized = validate_document(document)
    record = ThingCatalogWriteService(session).create(sanitized)
    return serialize_thing(record, include_document=True)


@router.put("/things/{thing_id:path}")
def update_owned_thing(
    thing_id: str,
    session: SessionDep,
    document: dict[str, Any] = Body(...),
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    sanitized = validate_document(document)
    decoded_thing_id = decode_thing_id(thing_id)
    record = ThingCatalogWriteService(session).update(decoded_thing_id, sanitized)
    return serialize_thing(record, include_document=True)


@router.delete("/things/{thing_id:path}")
def delete_owned_thing(
    thing_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:delete"])),
) -> dict[str, str]:
    decoded_thing_id = decode_thing_id(thing_id)
    ThingCatalogWriteService(session).delete(decoded_thing_id)
    return {"id": decoded_thing_id, "status": "deleted"}


router.include_router(credentials_router)
