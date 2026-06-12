import contextlib
import io
import json
import unittest
from types import SimpleNamespace

from copilot.virtual_things.handler import RESULT_PREFIX, HandlerContext, handler_wrapper


def _fake_wot(**overrides):
    base = {
        "read_property": lambda *a, **k: 42,
        "write_property": lambda *a, **k: None,
        "invoke_action": lambda *a, **k: {"ok": True},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _run(code: str, wot) -> dict:
    namespace = {"wot": wot}
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exec(code, namespace)
    for line in reversed(stdout.getvalue().splitlines()):
        if line.startswith(RESULT_PREFIX):
            return json.loads(line.removeprefix(RESULT_PREFIX))
    raise AssertionError("handler produced no result line")


def _context(capabilities):
    return HandlerContext(
        thing_id="virtual:thing",
        affordance_type="action",
        affordance_name="disaggregate",
        capabilities=capabilities,
        config={},
    )


class VirtualThingGuardedWotTestCase(unittest.TestCase):
    def test_declared_capability_call_succeeds(self) -> None:
        """Regression: the guard class referenced ``__vt_check`` which Python
        name-mangled, raising NameError the first time a handler hit a real
        capability call."""
        code = handler_wrapper(
            handler_code=(
                "def handle(input, state, context):\n"
                "    return wot.invoke_action('urn:nilm', 'disaggregate', input)"
            ),
            input_value={"series": [1, 2, 3]},
            state={},
            context=_context(
                [{"thing_id": "urn:nilm", "ops": ["invokeAction"], "affordances": ["disaggregate"]}]
            ),
        )

        result = _run(code, _fake_wot(invoke_action=lambda *a, **k: {"fridge": 0.4}))

        self.assertEqual(result, {"fridge": 0.4})

    def test_undeclared_capability_is_blocked(self) -> None:
        code = handler_wrapper(
            handler_code=(
                "def handle(input, state, context):\n"
                "    return wot.read_property('urn:secret', 'power')"
            ),
            input_value=None,
            state={},
            context=_context(
                [{"thing_id": "urn:nilm", "ops": ["invokeAction"], "affordances": ["disaggregate"]}]
            ),
        )

        with self.assertRaises(PermissionError):
            _run(code, _fake_wot())


if __name__ == "__main__":
    unittest.main()
