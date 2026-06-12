import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from copilot.agent.tools.virtual_things import define_virtual_thing, draft_virtual_thing_definition
from copilot.virtual_things.capabilities import infer_capabilities
from copilot.virtual_things.dispatcher import _RESULT_PREFIX, VirtualThingDispatcher
from copilot.virtual_things.schemas import DefineVirtualThingRequest, VirtualThingBindingSpec
from copilot.virtual_things.validator import VirtualThingValidator


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
        self.enqueued_emission = None

    def get_binding(self, **_kwargs):
        return self.binding

    def update_binding_state(self, *, binding_id, state):
        self.updated_state = (binding_id, state)

    def enqueue_event_emission(self, *, thing_id, event_name, payload):
        self.enqueued_emission = (thing_id, event_name, payload)


class _FakeExecutor:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0
        self.kwargs = []

    async def execute(self, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        result = self.results.pop(0)
        return {"stdout": f"{_RESULT_PREFIX}{result}"}


class _LocalExecutor:
    async def execute(self, *, session_id, code, timeout_seconds=None):
        stdout = io.StringIO()
        namespace = {
            "wot": SimpleNamespace(
                read_property=lambda *_args, **_kwargs: None,
                write_property=lambda *_args, **_kwargs: None,
                invoke_action=lambda *_args, **_kwargs: None,
            )
        }
        with contextlib.redirect_stdout(stdout):
            exec(code, namespace, namespace)
        return {"stdout": stdout.getvalue()}


class VirtualThingSchemasTestCase(unittest.TestCase):
    def test_draft_tool_returns_canonical_define_args_for_hello_action(self):
        result = draft_virtual_thing_definition.invoke(
            {
                "spec": {
                    "title": "Hello World Virtual Thing",
                    "description": "Says hello.",
                    "actions": {
                        "sayHello": {
                            "output": {"type": "string"},
                            "handler_code": (
                                "def handle(input, state, context):\n    return 'hello world'"
                            ),
                        }
                    },
                }
            }
        )

        self.assertTrue(result["ok"])
        define_args = result["define_args"]
        self.assertEqual(define_args["title"], "Hello World Virtual Thing")
        self.assertEqual(define_args["thing_id"], result["thing_id"])
        self.assertIn("security", define_args["td"])
        self.assertEqual(
            define_args["bindings"],
            [
                {
                    "affordance_type": "action",
                    "affordance_name": "sayHello",
                    "kind": "computed",
                    "handler_code": "def handle(input, state, context):\n    return 'hello world'",
                    "config": {},
                    "capabilities": [],
                    "timeout_seconds": 30,
                    "cache_ttl_seconds": 30,
                }
            ],
        )

    def test_draft_tool_accepts_computed_property_schema(self):
        result = draft_virtual_thing_definition.invoke(
            {
                "spec": {
                    "title": "Comfort Score",
                    "properties": {
                        "currentScore": {
                            "schema": {"type": "number", "readOnly": True},
                            "cache_ttl_seconds": 5,
                            "handler_code": "def handle(input, state, context):\n    return 72",
                        }
                    },
                }
            }
        )

        self.assertTrue(result["ok"])
        define_args = result["define_args"]
        self.assertEqual(define_args["td"]["properties"]["currentScore"]["type"], "number")
        self.assertEqual(define_args["bindings"][0]["cache_ttl_seconds"], 5)

    def test_draft_tool_accepts_interval_event(self):
        result = draft_virtual_thing_definition.invoke(
            {
                "spec": {
                    "title": "Counter Event Thing",
                    "events": {
                        "tick": {
                            "data": {"type": "object"},
                            "trigger": {"kind": "interval", "interval_seconds": 10},
                            "state": {"counter": 0},
                            "handler_code": (
                                "def handle(input, state, context):\n"
                                "    state = state or {}\n"
                                "    counter = state.get('counter', 0) + 1\n"
                                "    return {'emit': True, 'payload': {'counter': counter}, "
                                "'state': {'counter': counter}}"
                            ),
                        }
                    },
                }
            }
        )

        self.assertTrue(result["ok"])
        binding = result["define_args"]["bindings"][0]
        self.assertEqual(binding["affordance_type"], "event")
        self.assertEqual(binding["kind"], "emitted")
        self.assertEqual(binding["trigger"], {"kind": "interval", "interval_seconds": 10})
        self.assertEqual(binding["state"], {"counter": 0})

    def test_draft_tool_accepts_source_event_trigger(self):
        result = draft_virtual_thing_definition.invoke(
            {
                "spec": {
                    "title": "Door Edge Signal",
                    "events": {
                        "openedEdge": {
                            "data": {"type": "object"},
                            "trigger": {
                                "kind": "source_event",
                                "thing_id": "urn:source-door",
                                "event_name": "opened",
                            },
                            "handler_code": (
                                "def handle(input, state, context):\n"
                                "    return {'emit': True, 'payload': input, 'state': state}"
                            ),
                        }
                    },
                }
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["define_args"]["bindings"][0]["trigger"],
            {
                "kind": "source_event",
                "thing_id": "urn:source-door",
                "event_name": "opened",
            },
        )

    def test_draft_tool_accepts_explicit_event_trigger(self):
        result = draft_virtual_thing_definition.invoke(
            {
                "spec": {
                    "title": "Manual Signal",
                    "events": {
                        "signal": {
                            "data": {"type": "object"},
                            "trigger": {"kind": "explicit"},
                            "handler_code": (
                                "def handle(input, state, context):\n"
                                "    return {'emit': True, 'payload': input.get('input'), "
                                "'state': state}"
                            ),
                        }
                    },
                }
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["define_args"]["bindings"][0]["trigger"], {"kind": "explicit"})

    def test_draft_tool_rejects_event_without_trigger(self):
        result = draft_virtual_thing_definition.invoke(
            {
                "spec": {
                    "title": "Broken Event Thing",
                    "events": {
                        "tick": {
                            "data": {"type": "object"},
                            "handler_code": (
                                "def handle(input, state, context):\n"
                                "    return {'emit': True, 'payload': input, 'state': state}"
                            ),
                        }
                    },
                }
            }
        )

        self.assertIn("requires trigger", result["error"])

    def test_draft_tool_rejects_missing_handler(self):
        result = draft_virtual_thing_definition.invoke(
            {
                "spec": {
                    "title": "Broken Action Thing",
                    "actions": {"sayHello": {"output": {"type": "string"}}},
                }
            }
        )

        self.assertIn("requires handler_code", result["error"])

    def test_draft_tool_rejects_javascript_handler(self):
        result = draft_virtual_thing_definition.invoke(
            {
                "spec": {
                    "title": "Broken JS Thing",
                    "actions": {
                        "sayHello": {
                            "output": {"type": "string"},
                            "handler_code": (
                                "function handle(input, state, context) { return 'hello world'; }"
                            ),
                        }
                    },
                }
            }
        )

        self.assertIn("must be Python code", result["error"])

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

    def test_define_request_accepts_event_binding_shorthand(self):
        request = DefineVirtualThingRequest(
            title="Counter Event Thing",
            td={
                "events": {
                    "tick": {
                        "data": {
                            "type": "object",
                            "properties": {"counter": {"type": "integer"}},
                        },
                        "evaluationInterval": 10000,
                    }
                }
            },
            bindings=[
                {
                    "affordance": "tick",
                    "kind": "event",
                    "source": (
                        "def handle(input, state, context):\n"
                        "    state = state or {}\n"
                        "    counter = int(state.get('counter', 0)) + 1\n"
                        "    return {'emit': True, 'payload': {'counter': counter}, "
                        "'state': {'counter': counter}}"
                    ),
                    "state": {"counter": 0},
                }
            ],
        )

        binding = request.bindings[0]
        self.assertEqual(binding.affordance_type, "event")
        self.assertEqual(binding.affordance_name, "tick")
        self.assertEqual(binding.kind, "emitted")
        self.assertEqual(binding.trigger.interval_seconds if binding.trigger else None, 10)


class VirtualThingCapabilityInferenceTestCase(unittest.TestCase):
    def test_infers_grants_for_each_source_thing(self):
        handler = (
            "def handle(input, state, context):\n"
            "    forecast = wot.read_property('urn:dev:forecast', 'nextHourKw')\n"
            "    usage = wot.read_property('urn:dev:meter', 'powerKw')\n"
            "    wot.invoke_action('urn:dev:meter', 'reset')\n"
            "    return forecast - usage"
        )

        capabilities = infer_capabilities(handler)

        self.assertEqual(
            capabilities,
            [
                {
                    "thing_id": "urn:dev:forecast",
                    "ops": ["readProperty"],
                    "affordances": ["nextHourKw"],
                },
                {
                    "thing_id": "urn:dev:meter",
                    "ops": ["invokeAction", "readProperty"],
                    "affordances": ["powerKw", "reset"],
                },
            ],
        )

    def test_dynamic_thing_id_is_not_inferred(self):
        handler = (
            "def handle(input, state, context):\n"
            "    target = context['config']['thing_id']\n"
            "    return wot.read_property(target, 'value')"
        )

        self.assertEqual(infer_capabilities(handler), [])

    def test_dynamic_affordance_grants_all_affordances(self):
        handler = (
            "def handle(input, state, context):\n"
            "    return wot.read_property('urn:dev:meter', input['name'])"
        )

        self.assertEqual(
            infer_capabilities(handler),
            [{"thing_id": "urn:dev:meter", "ops": ["readProperty"], "affordances": []}],
        )

    def test_binding_merges_explicit_and_inferred_capabilities(self):
        binding = VirtualThingBindingSpec(
            affordance_type="property",
            affordance_name="headroom",
            kind="computed",
            handler_code=(
                "def handle(input, state, context):\n"
                "    return wot.read_property('urn:dev:meter', 'powerKw')"
            ),
            capabilities=[
                {
                    "thing_id": "urn:dev:forecast",
                    "ops": ["readProperty"],
                    "affordances": ["nextHourKw"],
                }
            ],
        )

        grants = {cap.thing_id: cap for cap in binding.capabilities}
        self.assertEqual(set(grants), {"urn:dev:forecast", "urn:dev:meter"})
        self.assertEqual(grants["urn:dev:meter"].ops, ["readProperty"])
        self.assertEqual(grants["urn:dev:meter"].affordances, ["powerKw"])

    def test_draft_tool_attaches_inferred_capabilities(self):
        result = draft_virtual_thing_definition.invoke(
            {
                "spec": {
                    "title": "Grid Headroom",
                    "properties": {
                        "headroom": {
                            "schema": {"type": "number"},
                            "handler_code": (
                                "def handle(input, state, context):\n"
                                "    f = wot.read_property('urn:dev:forecast', 'nextHourKw')\n"
                                "    u = wot.read_property('urn:dev:meter', 'powerKw')\n"
                                "    return f - u"
                            ),
                        }
                    },
                }
            }
        )

        self.assertTrue(result["ok"], result)
        capabilities = result["define_args"]["bindings"][0]["capabilities"]
        thing_ids = {cap["thing_id"] for cap in capabilities}
        self.assertEqual(thing_ids, {"urn:dev:forecast", "urn:dev:meter"})


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
            timeout_seconds=7,
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
        self.assertEqual(executor.kwargs[0]["timeout_seconds"], 7)

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
            timeout_seconds=30,
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

    async def test_event_evaluate_defaults_missing_state_to_empty_object(self):
        binding = SimpleNamespace(
            id="event-binding",
            thing_id="virtual:things:counter",
            affordance_type="event",
            affordance_name="tick",
            kind="emitted",
            handler_code=(
                "def handle(input, state, context):\n"
                "    counter = state.get('counter', 0) + 1\n"
                "    return {'emit': True, 'payload': {'counter': counter}, "
                "'state': {'counter': counter}}"
            ),
            capabilities=[],
            config={},
            state=None,
            timeout_seconds=30,
            cache_ttl_seconds=0,
        )
        store = _FakeStore(binding)
        dispatcher = VirtualThingDispatcher(
            store=store,
            record_store=SimpleNamespace(),
            code_executor=_LocalExecutor(),
        )

        self.assertEqual(
            await dispatcher.evaluate_event("virtual:things:counter", "tick", {}),
            {"counter": 1},
        )
        self.assertEqual(store.updated_state, ("event-binding", {"counter": 1}))

    async def test_event_evaluate_dry_run_does_not_persist_state(self):
        binding = SimpleNamespace(
            id="event-binding",
            thing_id="virtual:things:counter",
            affordance_type="event",
            affordance_name="tick",
            kind="emitted",
            handler_code=(
                "def handle(input, state, context):\n"
                "    return {'emit': True, 'payload': {'counter': 1}, "
                "'state': {'counter': 1}}"
            ),
            capabilities=[],
            config={},
            state=None,
            timeout_seconds=30,
            cache_ttl_seconds=0,
        )
        store = _FakeStore(binding)
        dispatcher = VirtualThingDispatcher(
            store=store,
            record_store=SimpleNamespace(),
            code_executor=_LocalExecutor(),
        )

        self.assertEqual(
            await dispatcher.evaluate_event("virtual:things:counter", "tick", {}, dry_run=True),
            {"counter": 1},
        )
        self.assertIsNone(store.updated_state)

    async def test_event_evaluate_rejects_none_result_with_hint(self):
        binding = SimpleNamespace(
            id="event-binding",
            thing_id="virtual:things:counter",
            affordance_type="event",
            affordance_name="tick",
            kind="emitted",
            handler_code="def handle(input, state, context):\n    return None",
            capabilities=[],
            config={},
            state=None,
            timeout_seconds=30,
            cache_ttl_seconds=0,
        )
        dispatcher = VirtualThingDispatcher(
            store=_FakeStore(binding),
            record_store=SimpleNamespace(),
            code_executor=_FakeExecutor(["null"]),
        )

        with self.assertRaisesRegex(ValueError, "returned None"):
            await dispatcher.evaluate_event("virtual:things:counter", "tick", {})

    async def test_emit_event_enqueues_emission_when_handler_emits(self):
        binding = SimpleNamespace(
            id="event-binding",
            thing_id="virtual:things:manual",
            affordance_type="event",
            affordance_name="signal",
            kind="emitted",
            handler_code=(
                "def handle(input, state, context):\n"
                "    return {'emit': True, 'payload': input['input'], 'state': state}"
            ),
            capabilities=[],
            config={},
            state=None,
            timeout_seconds=30,
            cache_ttl_seconds=0,
        )
        store = _FakeStore(binding)
        dispatcher = VirtualThingDispatcher(
            store=store,
            record_store=SimpleNamespace(),
            code_executor=_LocalExecutor(),
        )

        result = await dispatcher.emit_event(
            "virtual:things:manual",
            "signal",
            {"trigger": "explicit", "input": {"ok": True}},
        )

        self.assertEqual(
            result,
            {
                "thing_id": "virtual:things:manual",
                "event_name": "signal",
                "emitted": True,
                "payload": {"ok": True},
            },
        )
        self.assertEqual(
            store.enqueued_emission,
            ("virtual:things:manual", "signal", {"ok": True}),
        )


class VirtualThingValidatorTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_smoke_validation_defaults_missing_event_state(self):
        request = DefineVirtualThingRequest(
            title="Counter Tick Event",
            td={
                "events": {
                    "tick": {
                        "data": {
                            "type": "object",
                            "properties": {"counter": {"type": "integer"}},
                            "required": ["counter"],
                        }
                    }
                }
            },
            bindings=[
                {
                    "affordance_type": "event",
                    "affordance_name": "tick",
                    "kind": "emitted",
                    "trigger": {"kind": "interval", "interval_seconds": 10},
                    "handler_code": (
                        "def handle(input, state, context):\n"
                        "    counter = state.get('counter', 0) + 1\n"
                        "    return {'emit': True, 'payload': {'counter': counter}, "
                        "'state': {'counter': counter}}"
                    ),
                }
            ],
        )

        report = await VirtualThingValidator(code_executor=_LocalExecutor()).validate(
            request,
            run_smoke=True,
        )

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["smoke_tested"])

    async def test_smoke_validation_rejects_event_that_only_works_with_seed_state(self):
        request = DefineVirtualThingRequest(
            title="Counter Tick Event",
            td={
                "events": {
                    "tick": {
                        "data": {
                            "type": "object",
                            "properties": {"counter": {"type": "integer"}},
                            "required": ["counter"],
                        }
                    }
                }
            },
            bindings=[
                {
                    "affordance_type": "event",
                    "affordance_name": "tick",
                    "kind": "emitted",
                    "trigger": {"kind": "interval", "interval_seconds": 10},
                    "state": {"counter": 0},
                    "handler_code": (
                        "def handle(input, state, context):\n"
                        "    if state.get('counter') is not None:\n"
                        "        counter = state['counter'] + 1\n"
                        "        return {'emit': True, 'payload': {'counter': counter}, "
                        "'state': {'counter': counter}}"
                    ),
                }
            ],
        )

        report = await VirtualThingValidator(code_executor=_LocalExecutor()).validate(
            request,
            run_smoke=True,
        )

        self.assertFalse(report["ok"])
        self.assertIn("empty state", report["issues"][0]["message"])
        self.assertIn("returned None", report["issues"][0]["message"])

    async def test_smoke_validation_rejects_event_that_fails_on_next_state(self):
        request = DefineVirtualThingRequest(
            title="Counter Tick Event",
            td={
                "events": {
                    "tick": {
                        "data": {
                            "type": "object",
                            "properties": {"counter": {"type": "integer"}},
                            "required": ["counter"],
                        }
                    }
                }
            },
            bindings=[
                {
                    "affordance_type": "event",
                    "affordance_name": "tick",
                    "kind": "emitted",
                    "trigger": {"kind": "interval", "interval_seconds": 10},
                    "handler_code": (
                        "def handle(input, state, context):\n"
                        "    counter = state.get('counter', 0)\n"
                        "    if counter == 0:\n"
                        "        return {'emit': True, 'payload': {'counter': 1}, "
                        "'state': {'counter': 1}}\n"
                        "    return None"
                    ),
                }
            ],
        )

        report = await VirtualThingValidator(code_executor=_LocalExecutor()).validate(
            request,
            run_smoke=True,
        )

        self.assertFalse(report["ok"])
        self.assertIn("next state", report["issues"][0]["message"])
        self.assertIn("returned None", report["issues"][0]["message"])

    async def test_smoke_validation_rejects_event_payload_schema_mismatch(self):
        request = DefineVirtualThingRequest(
            title="Counter Tick Event",
            td={
                "events": {
                    "tick": {
                        "data": {
                            "type": "object",
                            "properties": {"counter": {"type": "integer"}},
                            "required": ["counter"],
                        }
                    }
                }
            },
            bindings=[
                {
                    "affordance_type": "event",
                    "affordance_name": "tick",
                    "kind": "emitted",
                    "trigger": {"kind": "interval", "interval_seconds": 10},
                    "handler_code": (
                        "def handle(input, state, context):\n"
                        "    return {'emit': True, 'payload': {'counter': 'bad'}, "
                        "'state': {}}"
                    ),
                }
            ],
        )

        report = await VirtualThingValidator(code_executor=_LocalExecutor()).validate(
            request,
            run_smoke=True,
        )

        self.assertFalse(report["ok"])
        self.assertIn("schema validation", report["issues"][0]["message"])

    async def test_define_tool_does_not_persist_when_active_validation_fails(self):
        class RejectingValidator:
            async def validate(self, _request, *, run_smoke):
                self.run_smoke = run_smoke
                return {
                    "ok": False,
                    "smoke_tested": True,
                    "issues": [{"phase": "smoke", "message": "boom"}],
                }

        validator = RejectingValidator()
        with (
            patch(
                "copilot.agent.tools.virtual_things.VirtualThingValidator",
                return_value=validator,
            ),
            patch("copilot.agent.tools.virtual_things.VirtualThingStore") as store_cls,
        ):
            result = await define_virtual_thing.ainvoke(
                {
                    "title": "Broken",
                    "td": {"properties": {"value": {"type": "number"}}},
                    "bindings": [
                        {
                            "affordance_type": "property",
                            "affordance_name": "value",
                            "kind": "computed",
                            "handler_code": "def handle(input, state, context):\n    return 1",
                        }
                    ],
                },
                config={"configurable": {"thread_id": "thread-1"}},
            )

        self.assertEqual(result["error"], "virtual thing validation failed")
        self.assertFalse(result["validation_report"]["ok"])
        self.assertTrue(validator.run_smoke)
        store_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
