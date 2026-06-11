from __future__ import annotations

import asyncio
from unittest.mock import patch

from copilot.rdf.schema import is_domain_iri, summarize_schema


def _uri_row(variable: str, iri: str, count: int) -> dict[str, object]:
    return {
        variable: {"type": "uri", "value": iri},
        "count": {"type": "literal", "value": str(count)},
    }


def test_is_domain_iri_excludes_wot_plumbing():
    assert is_domain_iri("https://saref.etsi.org/core/Sensor")
    assert not is_domain_iri("https://www.w3.org/2019/wot/td#hasForm")
    assert not is_domain_iri("http://www.w3.org/2011/http#methodName")
    assert not is_domain_iri("https://www.w3.org/2019/wot/security#BearerSecurityScheme")
    assert not is_domain_iri("https://www.w3.org/2019/wot/hypermedia#hasTarget")
    assert not is_domain_iri("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")


def test_summarize_schema_keeps_domain_and_drops_plumbing():
    class_rows = [
        _uri_row("class", "https://saref.etsi.org/core/Sensor", 12),
        _uri_row("class", "https://saref.etsi.org/saref4bldg/BuildingSpace", 4),
        _uri_row("class", "https://www.w3.org/2019/wot/security#BearerSecurityScheme", 3),
    ]
    predicate_rows = [
        _uri_row("predicate", "https://saref.etsi.org/saref4bldg/isContainedIn", 9),
        _uri_row("predicate", "https://www.w3.org/2019/wot/td#hasForm", 30),
        _uri_row("predicate", "http://www.w3.org/2011/http#methodName", 8),
        _uri_row("predicate", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", 40),
    ]

    summary = summarize_schema(class_rows=class_rows, predicate_rows=predicate_rows, limit=50)

    assert [c["iri"] for c in summary["classes"]] == [
        "https://saref.etsi.org/core/Sensor",
        "https://saref.etsi.org/saref4bldg/BuildingSpace",
    ]
    assert [p["iri"] for p in summary["predicates"]] == [
        "https://saref.etsi.org/saref4bldg/isContainedIn",
    ]
    assert summary["classes"][0]["count"] == 12
    assert summary["prefixes"] == {
        "saref": "https://saref.etsi.org/core/",
        "s4bldg": "https://saref.etsi.org/saref4bldg/",
    }


def test_summarize_schema_respects_limit():
    rows = [_uri_row("class", f"https://saref.etsi.org/core/C{i}", i) for i in range(5)]
    summary = summarize_schema(class_rows=rows, predicate_rows=[], limit=2)
    assert len(summary["classes"]) == 2


def test_describe_rdf_schema_tool_filters_and_calls_client_twice():
    from copilot.agent.tools.wot_registry import REGISTRY_TOOLS, describe_rdf_schema

    assert "describe_rdf_schema" in {tool.name for tool in REGISTRY_TOOLS}

    class FakeRdfClient:
        def __init__(self) -> None:
            self.queries: list[str] = []

        async def query(self, *, query: str, limit: int):
            self.queries.append(query)
            if "?class" in query:
                return {
                    "rows": [
                        _uri_row("class", "https://saref.etsi.org/core/Sensor", 3),
                        _uri_row("class", "https://www.w3.org/2019/wot/td#Thing", 5),
                    ]
                }
            return {
                "rows": [
                    _uri_row("predicate", "https://saref.etsi.org/core/hasState", 2),
                    _uri_row("predicate", "https://www.w3.org/2019/wot/td#hasForm", 9),
                ]
            }

    client = FakeRdfClient()
    with patch("copilot.agent.tools.wot_registry._rdf_client", return_value=client):
        result = asyncio.run(describe_rdf_schema.ainvoke({"limit": 50}))

    assert [c["iri"] for c in result["classes"]] == ["https://saref.etsi.org/core/Sensor"]
    assert [p["iri"] for p in result["predicates"]] == ["https://saref.etsi.org/core/hasState"]
    assert len(client.queries) == 2
