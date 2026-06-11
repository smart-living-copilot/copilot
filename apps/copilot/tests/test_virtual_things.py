import unittest
from types import SimpleNamespace

from copilot.virtual_things.dispatcher import _RESULT_PREFIX, VirtualThingDispatcher
from copilot.virtual_things.schemas import DefineVirtualThingRequest


def _base_td() -> dict:
    return {
        "@context": "https://www.w3.org/2022/wot/td/v1.1",
        "securityDefinitions": {"nosec_sc": {"scheme": "nosec"}},
        "security": "nosec_sc",
        "properties": {"temperature": {"type": "number"}},
        "actions": {"refresh": {"input": {"type": "object"}, "output": {"type": "number"}}},
        "events": {"threshold_crossed": {"data": {"type": "object"}}},
    }


class _FakeStore:
    def __init__(self, binding):
        self.binding = binding
        self.updated_state = None

    def get_binding(self, **_kwargs):
        return self.binding

    def update_binding_state(self, *, binding_id, state):
        self.updated_state = (binding_id, state)


class _FakeExecutor:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    async def execute(self, **_kwargs):
        self.calls += 1
        result = self.results.pop(0)
        return {"stdout": f"{_RESULT_PREFIX}{result}"}


class VirtualThingSchemasTestCase(unittest.TestCase):
    def test_define_request_injects_abstract_forms_and_validates_bindings(self):
        request = DefineVirtualThingRequest(
            title="Comfort Sensor",
            td=_base_td(),
            bindings=[
                {
                    "affordance_type": "property",
                    "affordance_name": "temperature",
                    "kind": "computed",
                    "handler_code": "def handle(input, state, context):\n    return 21",
                }
            ],
        )

        form = request.td["properties"]["temperature"]["forms"][0]
        self.assertEqual(form["op"], ["readproperty"])
        self.assertTrue(form["href"].startswith("urn:smart-living-copilot:virtual-things:"))

    def test_define_request_injects_default_security_boilerplate(self):
        request = DefineVirtualThingRequest(
            title="Comfort Sensor",
            td={"properties": {"temperature": {"type": "number"}}},
            bindings=[
                {
                    "affordance_type": "property",
                    "affordance_name": "temperature",
                    "kind": "computed",
                    "handler_code": "def handle(input, state, context):\n    return 21",
                }
            ],
        )

        self.assertEqual(request.td["@context"], "https://www.w3.org/2022/wot/td/v1.1")
        self.assertEqual(request.td["security"], "nosec_sc")
        self.assertEqual(request.td["securityDefinitions"]["nosec_sc"]["scheme"], "nosec")

    def test_define_request_rejects_missing_binding_affordance(self):
        with self.assertRaisesRegex(Exception, "missing property"):
            DefineVirtualThingRequest(
                title="Comfort Sensor",
                td=_base_td(),
                bindings=[
                    {
                        "affordance_type": "property",
                        "affordance_name": "missing",
                        "kind": "computed",
                        "handler_code": "def handle(input, state, context):\n    return 21",
                    }
                ],
            )

    def test_define_request_accepts_handle_alias_for_handler_code(self):
        request = DefineVirtualThingRequest(
            title="Comfort Sensor",
            td=_base_td(),
            bindings=[
                {
                    "affordance_type": "property",
                    "affordance_name": "temperature",
                    "kind": "computed",
                    "handle": "def handle(input, state, context):\n    return 21",
                }
            ],
        )

        self.assertIn("return 21", request.bindings[0].handler_code or "")

    def test_define_request_rejects_javascript_handler_with_clear_error(self):
        with self.assertRaisesRegex(Exception, "must be Python code"):
            DefineVirtualThingRequest(
                title="Comfort Sensor",
                td=_base_td(),
                bindings=[
                    {
                        "affordance_type": "property",
                        "affordance_name": "temperature",
                        "kind": "computed",
                        "handle": "function handle(input, state, context) { return 21; }",
                    }
                ],
            )


class VirtualThingDispatcherTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_computed_property_cache_lives_in_dispatcher(self):
        binding = SimpleNamespace(
            id="binding-1",
            thing_id="virtual:things:comfort",
            affordance_type="property",
            affordance_name="temperature",
            kind="computed",
            handler_code="def handle(input, state, context):\n    return 21",
            capabilities=[],
            config={},
            state=None,
            cache_ttl_seconds=30,
        )
        executor = _FakeExecutor(["21", "22"])
        dispatcher = VirtualThingDispatcher(
            store=_FakeStore(binding),
            record_store=SimpleNamespace(),
            code_executor=executor,
        )

        self.assertEqual(
            await dispatcher.read_property("virtual:things:comfort", "temperature"), 21
        )
        self.assertEqual(
            await dispatcher.read_property("virtual:things:comfort", "temperature"), 21
        )
        self.assertEqual(executor.calls, 1)

    async def test_event_evaluate_persists_state_and_suppresses_null_emit(self):
        binding = SimpleNamespace(
            id="event-binding",
            thing_id="virtual:things:comfort",
            affordance_type="event",
            affordance_name="threshold_crossed",
            kind="emitted",
            handler_code="def handle(input, state, context):\n    return {}",
            capabilities=[],
            config={},
            state={"was_below": False},
            cache_ttl_seconds=0,
        )
        store = _FakeStore(binding)
        dispatcher = VirtualThingDispatcher(
            store=store,
            record_store=SimpleNamespace(),
            code_executor=_FakeExecutor(
                ['{"emit": false, "payload": {"ignored": true}, "state": {"was_below": true}}']
            ),
        )

        self.assertIsNone(
            await dispatcher.evaluate_event(
                "virtual:things:comfort",
                "threshold_crossed",
                {"value": 19},
            )
        )
        self.assertEqual(store.updated_state, ("event-binding", {"was_below": True}))


if __name__ == "__main__":
    unittest.main()
