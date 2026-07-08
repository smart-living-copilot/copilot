from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from wotbot.catalog.events.outbox import enqueue_thing_event
from wotbot.core.database import get_session_factory
from wotbot.core.time import utc_now
from wotbot.jobs.records.td import build_virtual_record_td
from wotbot.virtual_things.db import VirtualThing, VirtualThingBinding
from wotbot.virtual_things.schemas import (
    DefineVirtualThingRequest,
    VirtualThingBindingSpec,
    VirtualThingCapability,
    VirtualThingDefinition,
    json_safe,
)


class VirtualThingStateConflict(RuntimeError):
    """Raised when shared state changed between handler read and write."""


@dataclass(frozen=True)
class VirtualThingRuntimeBinding:
    id: str
    thing_id: str
    affordance_type: str
    affordance_name: str
    kind: str
    handler_code: str | None
    config: dict[str, Any]
    capabilities: list[dict[str, Any]]
    trigger: Any | None
    state: Any
    timeout_seconds: int
    cache_ttl_seconds: int
    shared_state: dict[str, Any]
    shared_state_version: int


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
                    shared_state=json_safe(request.shared_state or {}),
                    shared_state_version=1,
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
                if request.shared_state is not None:
                    next_shared_state = json_safe(request.shared_state)
                    if next_shared_state != (existing.shared_state or {}):
                        existing.shared_state = next_shared_state
                        existing.shared_state_version += 1
                existing.updated_at = now

            self._replace_bindings(session, thing_id, request.bindings, now=now)
            enqueue_thing_event(session, _definition_event("update", thing_id, version))
            session.commit()
            return self.get_definition(thing_id, include_disabled=True)

    def apply_enrichment(
        self, thing_id: str, enriched_td: dict[str, Any], *, base_version: int
    ) -> bool:
        """Write a semantically enriched TD back, only if still at ``base_version``.

        Bindings are untouched (enrichment only annotates the TD). A version mismatch
        means the definition changed while enrichment ran — e.g. the Thing was
        re-activated with another affordance — so the stale result is dropped and the
        newer activation's own enrichment wins. Returns whether the write was applied.
        """
        with self._session_factory() as session:
            existing = session.get(VirtualThing, thing_id)
            if existing is None or existing.version != base_version:
                return False
            version = existing.version + 1
            existing.abstract_td = json_safe(enriched_td)
            existing.version = version
            existing.updated_at = utc_now()
            enqueue_thing_event(session, _definition_event("update", thing_id, version))
            session.commit()
            return True

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

    def get_runtime_binding(
        self,
        *,
        thing_id: str,
        affordance_type: str,
        affordance_name: str,
    ) -> VirtualThingRuntimeBinding:
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
            return _runtime_binding_from_rows(thing, binding)

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

    def update_shared_state(
        self,
        *,
        thing_id: str,
        expected_version: int,
        shared_state: dict[str, Any],
    ) -> int:
        with self._session_factory() as session:
            return self._update_shared_state(
                session,
                thing_id=thing_id,
                expected_version=expected_version,
                shared_state=shared_state,
                now=utc_now(),
            )

    def update_binding_and_shared_state(
        self,
        *,
        binding_id: str,
        state: Any,
        thing_id: str,
        expected_shared_state_version: int,
        shared_state: dict[str, Any],
        update_shared_state: bool,
    ) -> int | None:
        with self._session_factory() as session:
            binding = session.get(VirtualThingBinding, binding_id)
            if binding is None:
                raise KeyError(binding_id)
            now = utc_now()
            binding.state = json_safe(state)
            binding.updated_at = now
            next_version = None
            if update_shared_state:
                next_version = self._update_shared_state(
                    session,
                    thing_id=thing_id,
                    expected_version=expected_shared_state_version,
                    shared_state=shared_state,
                    now=now,
                    commit=False,
                )
            session.commit()
            return next_version

    def _update_shared_state(
        self,
        session: Session,
        *,
        thing_id: str,
        expected_version: int,
        shared_state: dict[str, Any],
        now: datetime,
        commit: bool = True,
    ) -> int:
        statement = (
            update(VirtualThing)
            .where(
                VirtualThing.id == thing_id,
                VirtualThing.shared_state_version == expected_version,
            )
            .values(
                shared_state=json_safe(shared_state),
                shared_state_version=VirtualThing.shared_state_version + 1,
                updated_at=now,
            )
            .returning(VirtualThing.shared_state_version)
        )
        next_version = session.scalar(statement)
        if next_version is None:
            if session.get(VirtualThing, thing_id) is None:
                raise KeyError(thing_id)
            raise VirtualThingStateConflict(
                f"shared state for {thing_id!r} changed; retry the interaction"
            )
        if commit:
            session.commit()
        return int(next_version)

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
                    "occurredAt": utc_now().isoformat(),
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
            shared_state=dict(row.shared_state or {}),
            shared_state_version=row.shared_state_version or 1,
            bindings=[_binding_spec_from_row(binding) for binding in binding_rows],
        )


def _runtime_binding_from_rows(
    thing: VirtualThing,
    binding: VirtualThingBinding,
) -> VirtualThingRuntimeBinding:
    return VirtualThingRuntimeBinding(
        id=binding.id,
        thing_id=binding.thing_id,
        affordance_type=binding.affordance_type,
        affordance_name=binding.affordance_name,
        kind=binding.kind,
        handler_code=binding.handler_code,
        config=dict(binding.config or {}),
        capabilities=list(binding.capabilities or []),
        trigger=binding.trigger,
        state=binding.state,
        timeout_seconds=binding.timeout_seconds,
        cache_ttl_seconds=binding.cache_ttl_seconds,
        shared_state=dict(thing.shared_state or {}),
        shared_state_version=thing.shared_state_version or 1,
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
        "occurredAt": utc_now().isoformat(),
    }
