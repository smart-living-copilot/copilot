from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from copilot.things.models import ThingConflictError, ThingDocument, ThingRecord
from copilot.things.events.outbox import enqueue_thing_event
from copilot.things.events import build_change_event, build_remove_event
from copilot.things.presentation import serialize_thing
from copilot.things.store import (
    create_thing,
    delete_thing,
    get_thing,
    list_things,
    put_thing,
)


class ThingCatalogQueryService:
    def __init__(self, session: Session):
        self._session = session

    def list_owned_things(
        self,
        *,
        query: str = "",
        page: int = 1,
        per_page: int = 25,
    ) -> dict[str, Any]:
        items, total = list_things(
            self._session,
            query=query,
            page=page,
            per_page=per_page,
        )
        return {
            "items": [serialize_thing(item) for item in items],
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    def get_owned_thing(self, thing_id: str) -> dict[str, Any]:
        record = self._get_thing_or_404(thing_id)
        return serialize_thing(record, include_document=True)

    def list_affordances(self, thing_id: str, kind: str) -> dict[str, Any]:
        record = self._get_thing_or_404(thing_id)
        return {
            "thing_id": thing_id,
            kind: self._extract_affordances(record, kind),
        }

    def get_affordance(self, thing_id: str, kind: str, name: str) -> dict[str, Any]:
        record = self._get_thing_or_404(thing_id)
        affordances = self._extract_affordances(record, kind)
        if name not in affordances:
            label = kind[:-1].capitalize()
            raise HTTPException(status_code=404, detail=f"{label} '{name}' not found")
        return {"name": name, "definition": affordances[name]}

    def _get_thing_or_404(self, thing_id: str) -> ThingRecord:
        record = get_thing(self._session, thing_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Thing not found")
        return record

    def _extract_affordances(self, record: ThingRecord, kind: str) -> dict[str, Any]:
        document = record.document if isinstance(record.document, dict) else {}
        return document.get(kind, {}) or {}


class ThingCatalogWriteService:
    def __init__(self, session: Session):
        self._session = session

    def create(self, document: ThingDocument) -> ThingRecord:
        try:
            record = create_thing(self._session, document, commit=False)
            enqueue_thing_event(
                self._session,
                build_change_event("create", record),
            )
            self._session.commit()
        except ThingConflictError as exc:
            self._session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            self._session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception:
            self._session.rollback()
            raise

        return record

    def update(self, thing_id: str, document: ThingDocument) -> ThingRecord:
        try:
            record, created = put_thing(
                self._session,
                thing_id,
                document,
                commit=False,
            )
            enqueue_thing_event(
                self._session,
                build_change_event("create" if created else "update", record),
            )
            self._session.commit()
        except ValueError as exc:
            self._session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            self._session.rollback()
            raise

        return record

    def delete(self, thing_id: str) -> None:
        try:
            deleted = delete_thing(self._session, thing_id, commit=False)
            if not deleted:
                self._session.rollback()
                raise HTTPException(status_code=404, detail="Thing not found")

            enqueue_thing_event(self._session, build_remove_event(thing_id))
            self._session.commit()
        except HTTPException:
            raise
        except Exception:
            self._session.rollback()
            raise
