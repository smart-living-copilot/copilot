import asyncio

import copilot.agent.tools.wot_registry as wot_registry_module


def test_wot_read_property_returns_decoded_value(monkeypatch):
    class FakeRuntimeClient:
        async def read_property(self, **_kwargs):
            return {
                "result": {
                    "success": True,
                    "payload": {
                        "kind": "inline",
                        "data": {"value": 21.5, "unit": "C"},
                    },
                }
            }

    monkeypatch.setattr(
        wot_registry_module,
        "_runtime_client",
        lambda: FakeRuntimeClient(),
    )

    response = asyncio.run(
        wot_registry_module.wot_read_property.ainvoke(
            {"thing_id": "sensor", "property_name": "temperature"}
        )
    )

    assert response == {"value": 21.5, "unit": "C"}


def test_wot_write_property_returns_tool_error_for_failed_interaction(monkeypatch):
    class FakeRuntimeClient:
        async def write_property(self, **_kwargs):
            return {
                "result": {
                    "success": False,
                    "status_text": "not writable",
                    "payload": {"kind": "inline", "data": None},
                }
            }

    monkeypatch.setattr(
        wot_registry_module,
        "_runtime_client",
        lambda: FakeRuntimeClient(),
    )

    response = asyncio.run(
        wot_registry_module.wot_write_property.ainvoke(
            {
                "thing_id": "lamp",
                "property_name": "brightness",
                "value": 40,
            }
        )
    )

    assert response == {"error": "not writable"}


def test_wot_invoke_action_returns_operation_handle(monkeypatch):
    class FakeRuntimeClient:
        async def invoke_action(self, **_kwargs):
            return {
                "outcome": "operation_handle",
                "operation_handle": {"operation_id": "op-1"},
            }

    monkeypatch.setattr(
        wot_registry_module,
        "_runtime_client",
        lambda: FakeRuntimeClient(),
    )

    response = asyncio.run(
        wot_registry_module.wot_invoke_action.ainvoke(
            {"thing_id": "device", "action_name": "start"}
        )
    )

    assert response == {"operation_id": "op-1"}


def test_wot_invoke_action_returns_decoded_completed_result(monkeypatch):
    class FakeRuntimeClient:
        async def invoke_action(self, **_kwargs):
            return {
                "outcome": "completed_result",
                "completed_result": {
                    "success": True,
                    "payload": {
                        "content_type": "application/json",
                        "data": {"status": "done"},
                    },
                },
            }

    monkeypatch.setattr(
        wot_registry_module,
        "_runtime_client",
        lambda: FakeRuntimeClient(),
    )

    response = asyncio.run(
        wot_registry_module.wot_invoke_action.ainvoke(
            {"thing_id": "device", "action_name": "start"}
        )
    )

    assert response == {"status": "done"}
