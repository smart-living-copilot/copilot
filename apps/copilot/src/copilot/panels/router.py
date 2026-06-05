from typing import Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from copilot.auth import User, require_scopes
from copilot.core.api_dependencies import SessionDep
from copilot.panels.render import wrap_panel_document
from copilot.panels.service import PanelService

router = APIRouter(prefix="/api", tags=["panels"])


class CreatePanelBody(BaseModel):
    title: str = ""
    html: str
    capabilities: list[dict[str, Any]] = []
    source_thread_id: str | None = None


class RenamePanelBody(BaseModel):
    title: str


@router.get("/panels")
def list_panels(
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return PanelService(session).list_panels()


@router.post("/panels")
def create_panel(
    session: SessionDep,
    body: CreatePanelBody = Body(...),
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    return PanelService(session).create_panel(
        title=body.title,
        html=body.html,
        capabilities=body.capabilities,
        source_thread_id=body.source_thread_id,
    )


@router.get("/panels/{panel_id}")
def get_panel(
    panel_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    return PanelService(session).get_panel(panel_id)


@router.get("/panels/{panel_id}/render", response_class=HTMLResponse)
def render_panel(
    panel_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:read"])),
) -> HTMLResponse:
    html, title = PanelService(session).get_render_payload(panel_id)
    return HTMLResponse(content=wrap_panel_document(html, title))


@router.patch("/panels/{panel_id}")
def rename_panel(
    panel_id: str,
    session: SessionDep,
    body: RenamePanelBody = Body(...),
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    return PanelService(session).rename_panel(panel_id, body.title)


@router.delete("/panels/{panel_id}")
def delete_panel(
    panel_id: str,
    session: SessionDep,
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, str]:
    PanelService(session).delete_panel(panel_id)
    return {"status": "deleted"}
