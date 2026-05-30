from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Query, Request

from copilot.auth import User, require_scopes
from copilot.core.api_dependencies import DatabaseDep
from copilot.search.service import SearchQueryService

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/things/search")
async def search_things(
    request: Request,
    connection: DatabaseDep,
    q: str = Query(..., min_length=1),
    k: int = Query(default=5, ge=1, le=20),
    _user: User = Depends(require_scopes(["search:read"])),
) -> dict[str, Any]:
    return await SearchQueryService(
        connection,
        request.app.state.search_service,
    ).search(query=q, k=k)


@router.get("/things/{thing_id:path}/index-status")
@router.get("/index-status/{thing_id:path}")
async def get_thing_index_status(
    thing_id: str,
    request: Request,
    connection: DatabaseDep,
    _user: User = Depends(require_scopes(["search:read"])),
) -> dict[str, Any]:
    decoded_id = unquote(thing_id)
    return await SearchQueryService(
        connection,
        request.app.state.search_service,
    ).get_index_status(decoded_id)
