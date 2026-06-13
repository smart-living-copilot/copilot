from __future__ import annotations

import pytest

from copilot.rdf.store import RdfStoreService
from copilot.virtual_things.derivation import DERIVED_FROM, PROV_NAMESPACE, PROV_PREFIX
from copilot.virtual_things.schemas import DefineVirtualThingRequest

_HANDLER = (
    "def handle(input, state, context):\n"
    "    t = wot.read_property('urn:thing:temp', 'temperature')\n"
    "    h = wot.read_property('urn:thing:humidity', 'humidity')\n"
    "    return (t + h) / 2\n"
)


def _computed_request() -> DefineVirtualThingRequest:
    return DefineVirtualThingRequest(
        title="Comfort Index",
        td={"properties": {"comfort_index": {"type": "number"}}},
        bindings=[
            {
                "affordance_type": "property",
                "affordance_name": "comfort_index",
                "kind": "computed",
                "handler_code": _HANDLER,
            }
        ],
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_computed_property_gets_prov_derivation_edges_from_read_sources():
    request = _computed_request()

    affordance = request.td["properties"]["comfort_index"]
    derived_from = affordance[DERIVED_FROM]
    source_ids = sorted(ref["@id"] for ref in derived_from)
    assert source_ids == ["urn:thing:humidity", "urn:thing:temp"]

    context = request.td["@context"]
    assert isinstance(context, list)
    prefix_map = next(item for item in context if isinstance(item, dict))
    assert prefix_map[PROV_PREFIX] == PROV_NAMESPACE


def test_pure_invoke_action_is_not_declared_derived():
    handler = (
        "def handle(input, state, context):\n"
        "    return wot.invoke_action('urn:thing:vent', 'open', {'pct': 50})\n"
    )
    request = DefineVirtualThingRequest(
        title="Open Vent",
        td={"actions": {"open_vent": {}}},
        bindings=[
            {
                "affordance_type": "action",
                "affordance_name": "open_vent",
                "kind": "computed",
                "handler_code": handler,
            }
        ],
    )

    assert DERIVED_FROM not in request.td["actions"]["open_vent"]


@pytest.mark.anyio
async def test_derivation_edge_is_discoverable_via_sparql(tmp_path):
    request = _computed_request()
    store = RdfStoreService(str(tmp_path / "rdf"))

    await store.upsert_thing(request.id, request.td)

    response = await store.query(
        query="""
            PREFIX td: <https://www.w3.org/2019/wot/td#>
            PREFIX prov: <http://www.w3.org/ns/prov#>
            SELECT ?name ?src WHERE {
                ?thing td:hasPropertyAffordance ?property .
                ?property td:name ?name ;
                    prov:wasDerivedFrom ?src .
            }
            ORDER BY ?src
        """,
        limit=100,
    )

    rows = response.get("rows")
    assert isinstance(rows, list)
    sources = [row["src"]["value"] for row in rows]
    assert sources == ["urn:thing:humidity", "urn:thing:temp"]
    assert all(row["name"]["value"] == "comfort_index" for row in rows)
