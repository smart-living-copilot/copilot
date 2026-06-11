from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from copilot.catalog.events.outbox import enqueue_thing_event
from copilot.core.database import get_session_factory
from copilot.jobs.records.td import build_virtual_record_td
from copilot.jobs.stores import utc_now
from copilot.virtual_things.db import VirtualThing, VirtualThingBinding
from copilot.virtual_things.schemas import (
    DefineVirtualThingRequest,
    VirtualThingBindingSpec,
    VirtualThingCapability,
    VirtualThingDefinition,
    json_safe,
)


class VirtualThingStore:
    """Stores abstract virtual Thing definitions and dispatch bindings."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    def define_thing(self, request: DefineVirtualThingRequest) -> VirtualThingDefinition:
        now = utc_now()
        thing_id = request.id or ""
        with self._session_factory() as session:
            existing = session.get(VirtualThing, thing_id)
            version = (existing.version + 1) if existing is not None else 1
            if existing is None:
                existing = VirtualThing(
                    id=thing_id,
                    title=request.title,
                    description=request.description,
                    owner_thread_id=request.owner_thread_id,
                    abstract_td=request.td,
                    version=version,
                    status=request.status,
                    created_at=now,
                    updated_at=now,
                )
                session.add(existing)
            else:
                existing.title = request.title
                existing.description = request.description
                existing.owner_thread_id = request.owner_thread_id
                existing.abstract_td = request.td
                existing.version = version
                existing.status = request.status
                existing.updated_at = now

            self._replace_bindings(session, thing_id, request.bindings, now=now)
            enqueue_thing_event(session, _definition_event("update", thing_id, version))
            session.commit()
            return self.get_definition(thing_id, include_disabled=True)

    def register_record_thing(
        self,
        *,
        thing_id: str,
        title: str,
        description: str,
        source_job_id: str,
        schema_version: int,
        record_schema: dict[str, Any],
    ) -> VirtualThingDefinition:
        td = build_virtual_record_td(
            thing_id=thing_id,
            title=title,
            description=description,
            record_schema=record_schema,
        )
        bindings: list[VirtualThingBindingSpec] = []
        for name in td.get("properties") or {}:
            bindings.append(
                VirtualThingBindingSpec(
                    affordance_type="property",
                    affordance_name=name,
                    kind="record",
                    config={
                        "source_job_id": source_job_id,
                        "schema_version": schema_version,
                    },
                    cache_ttl_seconds=0,
                )
            )
        for name in td.get("actions") or {}:
            bindings.append(
                VirtualThingBindingSpec(
                    affordance_type="action",
                    affordance_name=name,
                    kind="record",
                    config={
                        "source_job_id": source_job_id,
                        "schema_version": schema_version,
                    },
                    cache_ttl_seconds=0,
                )
            )
        return self.define_thing(
            DefineVirtualThingRequest(
                id=thing_id,
                title=title,
                description=description,
                td=td,
                bindings=bindings,
            )
        )

    def delete_thing(self, thing_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(VirtualThing, thing_id)
            if row is None:
                raise KeyError(thing_id)
            session.delete(row)
            enqueue_thing_event(session, _definition_event("delete", thing_id, row.version))
            session.commit()

    def set_status(self, thing_id: str, status: str) -> VirtualThingDefinition:
        if status not in {"active", "disabled"}:
            raise ValueError("status must be active or disabled")
        now = utc_now()
        with self._session_factory() as session:
            row = session.get(VirtualThing, thing_id)
            if row is None:
                raise KeyError(thing_id)
            row.status = status
            row.version += 1
            row.updated_at = now
            enqueue_thing_event(session, _definition_event("update", thing_id, row.version))
            session.commit()
            return self.get_definition(thing_id, include_disabled=True)

    def list_definitions(
        self,
        *,
        include_disabled: bool = False,
    ) -> list[VirtualThingDefinition]:
        with self._session_factory() as session:
            filters = []
            if not include_disabled:
                filters.append(VirtualThing.status == "active")
            rows = session.scalars(
                select(VirtualThing).where(*filters).order_by(VirtualThing.id)
            ).all()
            return [self._definition_from_row(session, row) for row in rows]

    def get_definition(
        self,
        thing_id: str,
        *,
        include_disabled: bool = False,
    ) -> VirtualThingDefinition:
        with self._session_factory() as session:
            row = session.get(VirtualThing, thing_id)
            if row is None or (row.status != "active" and not include_disabled):
                raise KeyError(thing_id)
            return self._definition_from_row(session, row)

    def get_binding(
        self,
        *,
        thing_id: str,
        affordance_type: str,
        affordance_name: str,
    ) -> VirtualThingBinding:
        with self._session_factory() as session:
            thing = session.get(VirtualThing, thing_id)
            if thing is None or thing.status != "active":
                raise KeyError(thing_id)
            binding = session.scalar(
                select(VirtualThingBinding).where(
                    VirtualThingBinding.thing_id == thing_id,
                    VirtualThingBinding.affordance_type == affordance_type,
                    VirtualThingBinding.affordance_name == affordance_name,
                )
            )
            if binding is None:
                raise KeyError(affordance_name)
            session.expunge(binding)
            return binding

    def update_binding_state(
        self,
        *,
        binding_id: str,
        state: Any,
    ) -> None:
        with self._session_factory() as session:
            binding = session.get(VirtualThingBinding, binding_id)
            if binding is None:
                raise KeyError(binding_id)
            binding.state = json_safe(state)
            binding.updated_at = utc_now()
            session.commit()

    def enqueue_event_emission(
        self,
        *,
        thing_id: str,
        event_name: str,
        payload: Any,
    ) -> None:
        with self._session_factory() as session:
            enqueue_thing_event(
                session,
                {
                    "eventType": "virtualThingEventEmissionRequested",
                    "id": thing_id,
                    "eventName": event_name,
                    "payload": json_safe(payload),
                    "hash": f"virtual-emission:{uuid4()}",
                    "occurredAt": datetime.now(timezone.utc).isoformat(),
                },
            )
            session.commit()

    def _replace_bindings(
        self,
        session: Session,
        thing_id: str,
        bindings: list[VirtualThingBindingSpec],
        *,
        now: datetime,
    ) -> None:
        existing = session.scalars(
            select(VirtualThingBinding).where(VirtualThingBinding.thing_id == thing_id)
        ).all()
        for row in existing:
            session.delete(row)
        session.flush()
        for binding in bindings:
            session.add(
                VirtualThingBinding(
                    id=str(uuid4()),
                    thing_id=thing_id,
                    affordance_type=binding.affordance_type,
                    affordance_name=binding.affordance_name,
                    kind=binding.kind,
                    handler_code=binding.handler_code,
                    config=json_safe(binding.config),
                    capabilities=[
                        capability.model_dump(mode="json") for capability in binding.capabilities
                    ],
                    trigger=(
                        binding.trigger.model_dump(mode="json")
                        if binding.trigger is not None
                        else None
                    ),
                    state=json_safe(binding.state),
                    timeout_seconds=binding.timeout_seconds,
                    cache_ttl_seconds=binding.cache_ttl_seconds,
                    created_at=now,
                    updated_at=now,
                )
            )

    def _definition_from_row(
        self,
        session: Session,
        row: VirtualThing,
    ) -> VirtualThingDefinition:
        binding_rows = session.scalars(
            select(VirtualThingBinding)
            .where(VirtualThingBinding.thing_id == row.id)
            .order_by(VirtualThingBinding.affordance_type, VirtualThingBinding.affordance_name)
        ).all()
        return VirtualThingDefinition(
            id=row.id,
            title=row.title,
            description=row.description,
            owner_thread_id=row.owner_thread_id,
            td=dict(row.abstract_td or {}),
            version=row.version,
            status=row.status,
            bindings=[_binding_spec_from_row(binding) for binding in binding_rows],
        )


def _binding_spec_from_row(row: VirtualThingBinding) -> VirtualThingBindingSpec:
    return VirtualThingBindingSpec(
        affordance_type=row.affordance_type,
        affordance_name=row.affordance_name,
        kind=row.kind,
        handler_code=row.handler_code,
        config=dict(row.config or {}),
        capabilities=[
            VirtualThingCapability.model_validate(capability)
            for capability in (row.capabilities or [])
        ],
        trigger=row.trigger,
        state=row.state,
        timeout_seconds=row.timeout_seconds,
        cache_ttl_seconds=row.cache_ttl_seconds,
    )


def _definition_event(action: str, thing_id: str, version: int) -> dict[str, Any]:
    return {
        "eventType": "virtualThingDefinitionChanged",
        "action": action,
        "id": thing_id,
        "hash": f"virtual-definition:{version}",
        "version": version,
        "occurredAt": datetime.now(timezone.utc).isoformat(),
    }
