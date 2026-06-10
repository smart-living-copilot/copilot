from __future__ import annotations

import pytest

from copilot.rdf.endpoint_context import (
    endpoint_context_from_document,
    extract_example_queries,
    validate_example_queries,
)


def _endpoint_document() -> dict[str, object]:
    return {
        "@context": [
            "https://www.w3.org/2022/wot/td/v1.1",
            {
                "sd": "http://www.w3.org/ns/sparql-service-description#",
                "void": "http://rdfs.org/ns/void#",
                "s4bldg": "https://saref.etsi.org/saref4bldg/",
                "slc": "https://smart-living-copilot.example/vocab#",
            },
        ],
        "@type": "sd:Service",
        "id": "urn:slc:endpoint:building-energy-kg",
        "title": "Building Energy KG",
        "description": "Building spaces and tariff data.",
        "tags": ["sparql-endpoint", "energy"],
        "sd:supportedLanguage": {"@id": "sd:SPARQL11Query"},
        "void:vocabulary": [{"@id": "https://saref.etsi.org/saref4bldg/"}],
        "void:classPartition": [
            {"void:class": {"@id": "s4bldg:BuildingSpace"}},
        ],
        "void:propertyPartition": [
            {"void:property": {"@id": "s4bldg:isSpaceOf"}},
        ],
        "slc:exampleQueries": [
            {
                "intent": "List spaces",
                "query": "SELECT ?space WHERE { ?space a <https://example.com/Space> }",
            }
        ],
    }


def test_endpoint_context_extracts_void_prefixes_and_examples():
    context = endpoint_context_from_document(
        thing_id="urn:slc:endpoint:building-energy-kg",
        document=_endpoint_document(),
    )

    assert context["id"] == "urn:slc:endpoint:building-energy-kg"
    assert context["title"] == "Building Energy KG"
    assert context["tags"] == ["sparql-endpoint", "energy"]
    assert context["prefixes"]["sd"] == "http://www.w3.org/ns/sparql-service-description#"
    assert context["prefixes"]["s4bldg"] == "https://saref.etsi.org/saref4bldg/"
    assert context["supportedLanguage"] == "sd:SPARQL11Query"
    assert context["void"]["vocabulary"] == ["https://saref.etsi.org/saref4bldg/"]
    assert context["void"]["classPartition"] == [
        {"void:class": "s4bldg:BuildingSpace"}
    ]
    assert context["void"]["propertyPartition"] == [
        {"void:property": "s4bldg:isSpaceOf"}
    ]
    assert context["exampleQueries"] == [
        {
            "intent": "List spaces",
            "query": "SELECT ?space WHERE { ?space a <https://example.com/Space> }",
        }
    ]


def test_extract_example_queries_returns_empty_for_absent_examples():
    assert extract_example_queries({"id": "urn:thing:no-examples"}) == []


def test_validate_example_queries_accepts_read_only_examples():
    validate_example_queries(_endpoint_document())


def test_validate_example_queries_rejects_malformed_examples():
    document = _endpoint_document()
    document["slc:exampleQueries"] = [{"intent": "", "query": "SELECT * WHERE { ?s ?p ?o }"}]

    with pytest.raises(ValueError, match="intent"):
        validate_example_queries(document)


def test_validate_example_queries_rejects_sparql_update():
    document = _endpoint_document()
    document["slc:exampleQueries"] = [
        {
            "intent": "Delete everything",
            "query": "DELETE WHERE { ?s ?p ?o }",
        }
    ]

    with pytest.raises(ValueError, match="read-only"):
        validate_example_queries(document)
