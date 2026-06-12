from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from copilot.auth import User
from copilot.auth.providers import get_current_user
from copilot.virtual_things.routes import router
from copilot.virtual_things.schemas import (
    DefineVirtualThingRequest,
    VirtualThingDefinition,
)

THING_ID = "virtual:things:comfort-sensor"


def _definition(
    *,
    status: str = "active",
    version: int = 1,
) -> VirtualThingDefinition:
    return VirtualThingDefinition(
        id=THING_ID,
        title="Comfort Sensor",
        description="Virtual comfort signal",
        td={
            "id": THING_ID,
            "title": "Comfort Sensor",
            "properties": {"temperature": {"type": "number"}},
        },
        version=version,
        status=status,  # type: ignore[arg-type]
        bindings=[
            {
                "affordance_type": "property",
                "affordance_name": "temperature",
                "kind": "computed",
                "handler_code": "def handle(input, state, context):\n    return 21",
            }
        ],
    )


class _FakeVirtualThingStore:
    definitions: dict[str, VirtualThingDefinition] = {}

    def list_definitions(
        self,
        *,
        include_disabled: bool = False,
    ) -> list[VirtualThingDefinition]:
        return [
            definition
            for definition in self.definitions.values()
            if include_disabled or definition.status == "active"
        ]

    def get_definition(
        self,
        thing_id: str,
        *,
        include_disabled: bool = False,
    ) -> VirtualThingDefinition:
        definition = self.definitions[thing_id]
        if definition.status != "active" and not include_disabled:
            raise KeyError(thing_id)
        return definition

    def define_thing(self, request: DefineVirtualThingRequest) -> VirtualThingDefinition:
        version = self.definitions.get(request.id or "", _definition()).version + 1
        definition = VirtualThingDefinition(
            id=request.id or THING_ID,
            title=request.title,
            description=request.description,
            owner_thread_id=request.owner_thread_id,
            td=request.td,
            version=version,
            status=request.status,
            bindings=request.bindings,
        )
        self.definitions[definition.id] = definition
        return definition

    def delete_thing(self, thing_id: str) -> None:
        del self.definitions[thing_id]


class _FakeValidator:
    async def validate(
        self,
        _request: DefineVirtualThingRequest,
        *,
        run_smoke: bool,
    ) -> dict[str, Any]:
        return {"ok": True, "smoke_tested": run_smoke, "issues": []}


def _client_for_user(user: User, monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(
        "copilot.virtual_things.routes.VirtualThingStore",
        _FakeVirtualThingStore,
    )
    monkeypatch.setattr(
        "copilot.virtual_things.routes.VirtualThingValidator",
        _FakeValidator,
    )
    _FakeVirtualThingStore.definitions = {THING_ID: _definition()}
    return TestClient(app)


def _define_payload() -> dict[str, Any]:
    return {
        "id": THING_ID,
        "title": "Comfort Sensor",
        "description": "Updated comfort signal",
        "td": {
            "id": THING_ID,
            "title": "Comfort Sensor",
            "properties": {"temperature": {"type": "number"}},
        },
        "status": "active",
        "bindings": [
            {
                "affordance_type": "property",
                "affordance_name": "temperature",
                "kind": "computed",
                "handler_code": "def handle(input, state, context):\n    return 22",
            }
        ],
    }


def test_virtual_things_routes_accept_api_key_user_with_thing_scopes(monkeypatch):
    user = User(
        user_id="admin-key",
        scopes=["things:read", "things:write", "things:delete"],
        auth_type="api_key",
    )

    with _client_for_user(user, monkeypatch) as client:
        list_response = client.get("/api/virtual-things/definitions")
        assert list_response.status_code == 200
        assert list_response.json()["definitions"][0]["id"] == THING_ID

        get_response = client.get(f"/api/virtual-things/definitions/{THING_ID}")
        assert get_response.status_code == 200
        assert get_response.json()["bindings"][0]["handler_code"].endswith("return 21")

        put_response = client.put(
            f"/api/virtual-things/definitions/{THING_ID}",
            json=_define_payload(),
        )
        assert put_response.status_code == 200
        assert put_response.json()["description"] == "Updated comfort signal"
        assert put_response.json()["bindings"][0]["handler_code"].endswith("return 22")

        delete_response = client.delete(f"/api/virtual-things/definitions/{THING_ID}")
        assert delete_response.status_code == 200
        assert delete_response.json() == {"ok": True, "thing_id": THING_ID}


def test_virtual_things_routes_reject_api_key_user_missing_scope(monkeypatch):
    user = User(
        user_id="writer-key",
        scopes=["things:write"],
        auth_type="api_key",
    )

    with _client_for_user(user, monkeypatch) as client:
        response = client.get("/api/virtual-things/definitions")

    assert response.status_code == 403
    assert response.json()["detail"] == "Missing required scopes: things:read"
