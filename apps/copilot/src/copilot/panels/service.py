from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from copilot.panels.models import Panel


def _serialize(panel: Panel, *, include_html: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": panel.id,
        "title": panel.title,
        "capabilities": panel.capabilities,
        "source_thread_id": panel.source_thread_id,
        "created_at": panel.created_at.isoformat() if panel.created_at else None,
        "updated_at": panel.updated_at.isoformat() if panel.updated_at else None,
    }
    if include_html:
        data["html"] = panel.html
    return data


class PanelService:
    def __init__(self, session: Session):
        self._session = session

    def list_panels(self) -> dict[str, Any]:
        panels = self._session.scalars(select(Panel).order_by(Panel.created_at.desc())).all()
        return {"items": [_serialize(panel) for panel in panels]}

    def create_panel(
        self,
        *,
        title: str,
        html: str,
        capabilities: list[dict[str, Any]],
        source_thread_id: str | None,
    ) -> dict[str, Any]:
        if not isinstance(html, str) or not html.strip():
            raise HTTPException(status_code=422, detail="html must not be empty")
        panel = Panel(
            id=uuid.uuid4().hex,
            title=title or "Untitled panel",
            html=html,
            capabilities=_clean_capabilities(capabilities),
            source_thread_id=source_thread_id,
        )
        self._session.add(panel)
        self._session.commit()
        self._session.refresh(panel)
        return _serialize(panel)

    def get_panel(self, panel_id: str, *, include_html: bool = False) -> dict[str, Any]:
        return _serialize(self._get_or_404(panel_id), include_html=include_html)

    def get_render_payload(self, panel_id: str) -> tuple[str, str]:
        panel = self._get_or_404(panel_id)
        return panel.html, panel.title

    def get_render_payload_with_capabilities(self, panel_id: str) -> dict[str, Any]:
        panel = self._get_or_404(panel_id)
        return {
            "html": panel.html,
            "title": panel.title,
            "capabilities": panel.capabilities or [],
        }

    def update_panel(
        self,
        panel_id: str,
        *,
        title: str | None = None,
        html: str | None = None,
        capabilities: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        panel = self._get_or_404(panel_id)
        if title is not None and title.strip():
            panel.title = title
        if html is not None:
            if not html.strip():
                raise HTTPException(status_code=422, detail="html must not be empty")
            panel.html = html
        if capabilities is not None:
            panel.capabilities = _clean_capabilities(capabilities)
        self._session.commit()
        self._session.refresh(panel)
        return _serialize(panel)

    def delete_panel(self, panel_id: str) -> None:
        panel = self._get_or_404(panel_id)
        self._session.delete(panel)
        self._session.commit()

    def _get_or_404(self, panel_id: str) -> Panel:
        panel = self._session.get(Panel, panel_id)
        if panel is None:
            raise HTTPException(status_code=404, detail="Panel not found")
        return panel


def _clean_capabilities(capabilities: Any) -> list[dict[str, Any]]:
    if not isinstance(capabilities, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for entry in capabilities:
        if not isinstance(entry, dict):
            continue
        thing_id = entry.get("thingId")
        ops = entry.get("ops")
        if not isinstance(thing_id, str) or not thing_id or not isinstance(ops, list):
            continue
        affordances = entry.get("affordances")
        cleaned.append(
            {
                "thingId": thing_id,
                "affordances": [a for a in affordances if isinstance(a, str)]
                if isinstance(affordances, list)
                else [],
                "ops": [op for op in ops if isinstance(op, str)],
            }
        )
    return cleaned
