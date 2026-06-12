"""Infer source-Thing capability grants from virtual Thing handler code.

A handler reaches real Things through the injected ``wot`` client:

    wot.read_property(thing_id, property_name)
    wot.write_property(thing_id, property_name, value)
    wot.invoke_action(thing_id, action_name, input)

The runtime guard rejects any call that is not pre-declared in the binding's
``capabilities``. Authoring those grants by hand is the step LLMs most often get
wrong, so we derive them statically from the handler's literal ``wot`` calls and
union them with anything the author declared explicitly.
"""

from __future__ import annotations

import ast
from typing import Any

_OP_BY_METHOD = {
    "read_property": "readProperty",
    "write_property": "writeProperty",
    "invoke_action": "invokeAction",
}
_NAME_KEYWORDS = ("property_name", "action_name", "name")

# Marks an argument that is present but not a string literal (e.g. a variable).
_DYNAMIC = object()


def infer_capabilities(handler_code: str | None) -> list[dict[str, Any]]:
    """Return capability grants implied by literal ``wot`` calls in the handler."""
    if not handler_code:
        return []
    try:
        tree = ast.parse(handler_code)
    except SyntaxError:
        return []

    grants: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "wot"):
            continue
        op = _OP_BY_METHOD.get(func.attr)
        if op is None:
            continue

        thing_id = _string_arg(node, 0, ("thing_id",))
        if not isinstance(thing_id, str):
            # Dynamic or missing thing_id cannot be scoped; author must declare it.
            continue
        name = _string_arg(node, 1, _NAME_KEYWORDS)

        grant = grants.get(thing_id)
        if grant is None:
            grant = {"ops": set(), "affordances": set(), "all_affordances": False}
            grants[thing_id] = grant
            order.append(thing_id)
        grant["ops"].add(op)
        if isinstance(name, str):
            grant["affordances"].add(name)
        else:
            # Dynamic/absent affordance name -> grant every affordance on this Thing.
            grant["all_affordances"] = True

    return [
        {
            "thing_id": thing_id,
            "ops": sorted(grants[thing_id]["ops"]),
            "affordances": (
                []
                if grants[thing_id]["all_affordances"]
                else sorted(grants[thing_id]["affordances"])
            ),
        }
        for thing_id in order
    ]


def _string_arg(node: ast.Call, index: int, keywords: tuple[str, ...]) -> Any:
    """Return a literal string argument, ``_DYNAMIC`` if present but non-literal."""
    if len(node.args) > index:
        return _literal(node.args[index])
    for keyword in node.keywords:
        if keyword.arg in keywords:
            return _literal(keyword.value)
    return None


def _literal(value: ast.expr) -> Any:
    if isinstance(value, ast.Constant):
        return value.value
    return _DYNAMIC
