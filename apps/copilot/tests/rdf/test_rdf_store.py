from __future__ import annotations

import pytest

from copilot.rdf.iris import RDF_THING_GRAPH_PREFIX, thing_graph_iri
from copilot.rdf.runtime import RdfStreamConfig
from copilot.rdf.store import RdfStoreService, sparql_query_kind


def _jsonld_thing(thing_id: str, name: str) -> dict[str, object]:
    return {
        "@context": {
            "name": "http://schema.org/name",
            "kind": "http://example.com/kind",
        },
        "@id": thing_id,
        "id": thing_id,
        "name": name,
        "kind": "sensor",
    }


def _values(response: dict[str, object], variable: str) -> list[str]:
    rows = response.get("rows")
    assert isinstance(rows, list)
    values: list[str] = []
    for row in rows:
        assert isinstance(row, dict)
        binding = row.get(variable)
        assert isinstance(binding, dict)
        value = binding.get("value")
        assert isinstance(value, str)
        values.append(value)
    return values


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_thing_graph_iri_encodes_thing_id():
    assert (
        thing_graph_iri("urn:thing:kitchen sensor")
        == f"{RDF_THING_GRAPH_PREFIX}urn%3Athing%3Akitchen%20sensor"
    )


def test_sparql_query_kind_allows_only_read_queries():
    assert sparql_query_kind("PREFIX schema: <http://schema.org/> SELECT * WHERE { ?s ?p ?o }")
    assert sparql_query_kind("ASK WHERE { ?s ?p ?o }") == "ASK"

    with pytest.raises(ValueError, match="read-only"):
        sparql_query_kind("DELETE WHERE { ?s ?p ?o }")


@pytest.mark.anyio
async def test_rdf_store_loads_each_thing_into_its_own_named_graph(tmp_path):
    store = RdfStoreService(str(tmp_path / "rdf"))
    await store.upsert_thing("urn:thing:alpha", _jsonld_thing("urn:thing:alpha", "Alpha"))
    await store.upsert_thing("urn:thing:beta", _jsonld_thing("urn:thing:beta", "Beta"))

    response = await store.query(
        query="""
            PREFIX schema: <http://schema.org/>
            SELECT ?graph ?name WHERE {
                GRAPH ?graph { ?thing schema:name ?name }
            }
            ORDER BY ?name
        """,
        limit=10,
    )

    assert response["type"] == "select"
    assert _values(response, "name") == ["Alpha", "Beta"]
    assert _values(response, "graph") == [
        thing_graph_iri("urn:thing:alpha"),
        thing_graph_iri("urn:thing:beta"),
    ]


@pytest.mark.anyio
async def test_rdf_store_queries_named_graphs_through_default_union(tmp_path):
    store = RdfStoreService(str(tmp_path / "rdf"))
    await store.upsert_thing("urn:thing:alpha", _jsonld_thing("urn:thing:alpha", "Alpha"))
    await store.upsert_thing("urn:thing:beta", _jsonld_thing("urn:thing:beta", "Beta"))

    response = await store.query(
        query="""
            PREFIX schema: <http://schema.org/>
            SELECT ?name WHERE {
                ?thing schema:name ?name .
            }
            ORDER BY ?name
        """,
        limit=10,
        use_default_graph_as_union=True,
    )

    assert _values(response, "name") == ["Alpha", "Beta"]


@pytest.mark.anyio
async def test_rdf_store_serializes_construct_results(tmp_path):
    store = RdfStoreService(str(tmp_path / "rdf"))
    await store.upsert_thing("urn:thing:alpha", _jsonld_thing("urn:thing:alpha", "Alpha"))

    response = await store.query(
        query="""
            PREFIX schema: <http://schema.org/>
            CONSTRUCT { ?thing schema:name ?name } WHERE {
                ?thing schema:name ?name .
            }
        """,
        limit=10,
    )

    assert response["type"] == "construct"
    assert response["format"] == "application/n-triples"
    assert '"Alpha"' in response["rdf"]


@pytest.mark.anyio
async def test_rdf_store_update_replaces_only_target_graph(tmp_path):
    store = RdfStoreService(str(tmp_path / "rdf"))
    await store.upsert_thing("urn:thing:alpha", _jsonld_thing("urn:thing:alpha", "Old Alpha"))
    await store.upsert_thing("urn:thing:beta", _jsonld_thing("urn:thing:beta", "Beta"))
    await store.upsert_thing("urn:thing:alpha", _jsonld_thing("urn:thing:alpha", "New Alpha"))

    response = await store.query(
        query="""
            PREFIX schema: <http://schema.org/>
            SELECT ?name WHERE {
                ?thing schema:name ?name .
            }
            ORDER BY ?name
        """,
        limit=10,
    )

    assert _values(response, "name") == ["Beta", "New Alpha"]


@pytest.mark.anyio
async def test_rdf_store_delete_removes_only_target_graph(tmp_path):
    store = RdfStoreService(str(tmp_path / "rdf"))
    await store.upsert_thing("urn:thing:alpha", _jsonld_thing("urn:thing:alpha", "Alpha"))
    await store.upsert_thing("urn:thing:beta", _jsonld_thing("urn:thing:beta", "Beta"))

    await store.delete_thing("urn:thing:alpha")

    response = await store.query(
        query="""
            PREFIX schema: <http://schema.org/>
            SELECT ?name WHERE {
                ?thing schema:name ?name .
            }
        """,
        limit=10,
    )

    assert _values(response, "name") == ["Beta"]


@pytest.mark.anyio
async def test_rdf_store_process_event_handles_create_update_and_remove(tmp_path):
    store = RdfStoreService(str(tmp_path / "rdf"))

    await store.process_event(
        {
            **_jsonld_thing("urn:thing:alpha", "Alpha"),
            "eventType": "create",
            "hash": "abc",
        }
    )
    await store.process_event(
        {
            **_jsonld_thing("urn:thing:alpha", "Alpha Updated"),
            "eventType": "update",
            "hash": "def",
        }
    )

    updated = await store.query(
        query="PREFIX schema: <http://schema.org/> SELECT ?name WHERE { ?thing schema:name ?name }",
        limit=10,
    )
    assert _values(updated, "name") == ["Alpha Updated"]

    await store.process_event({"id": "urn:thing:alpha", "eventType": "remove"})
    removed = await store.query(
        query="PREFIX schema: <http://schema.org/> SELECT ?name WHERE { ?thing schema:name ?name }",
        limit=10,
    )
    assert removed["rows"] == []


def test_rdf_stream_config_reads_settings_values():
    class Settings:
        THING_EVENTS_STREAM = "thing_events"
        RDF_EVENTS_GROUP = "rdf_group"
        RDF_EVENTS_CONSUMER = "consumer_a"
        RDF_EVENTS_BATCH_SIZE = 25
        RDF_EVENTS_POLL_BLOCK_MS = 3000
        RDF_EVENTS_CLAIM_IDLE_MS = 45000
        RDF_EVENTS_RETRY_SECONDS = 7

    assert RdfStreamConfig.from_settings(Settings()) == RdfStreamConfig(
        stream="thing_events",
        group="rdf_group",
        consumer="consumer_a",
        batch_size=25,
        poll_block_ms=3000,
        claim_idle_ms=45000,
        retry_seconds=7,
    )
