from __future__ import annotations

from types import SimpleNamespace

import pytest

from copilot.rdf.endpoint_context import (
    endpoint_context_from_document,
    extract_example_queries,
    is_sparql_endpoint_document,
    load_all_endpoint_contexts,
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
        "sd:endpoint": {"@id": "https://example.com/sparql"},
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
    assert context["void"]["classPartition"] == [{"void:class": "s4bldg:BuildingSpace"}]
    assert context["void"]["propertyPartition"] == [{"void:property": "s4bldg:isSpaceOf"}]
    assert context["exampleQueries"] == [
        {
            "intent": "List spaces",
            "query": "SELECT ?space WHERE { ?space a <https://example.com/Space> }",
        }
    ]


def test_extract_example_queries_returns_empty_for_absent_examples():
    assert extract_example_queries({"id": "urn:thing:no-examples"}) == []


def test_is_sparql_endpoint_document_requires_service_endpoint_and_query_language():
    assert is_sparql_endpoint_document(_endpoint_document())

    missing_endpoint = _endpoint_document()
    missing_endpoint.pop("sd:endpoint", None)
    assert not is_sparql_endpoint_document(missing_endpoint)

    wrong_type = _endpoint_document()
    wrong_type["@type"] = "Thing"
    assert not is_sparql_endpoint_document(wrong_type)

    wrong_language = _endpoint_document()
    wrong_language["sd:supportedLanguage"] = {"@id": "sd:SPARQL10Query"}
    assert not is_sparql_endpoint_document(wrong_language)


def test_load_all_endpoint_contexts_skips_non_endpoint_things():
    class FakeScalarResult:
        def all(self):
            return [
                SimpleNamespace(id="urn:thing:lamp", document={"@type": "Thing"}),
                SimpleNamespace(
                    id="urn:slc:endpoint:building-energy-kg",
                    document=_endpoint_document(),
                ),
            ]

    class FakeSession:
        def scalars(self, _stmt):
            return FakeScalarResult()

    contexts = load_all_endpoint_contexts(FakeSession())  # type: ignore[arg-type]

    assert [context["id"] for context in contexts] == ["urn:slc:endpoint:building-energy-kg"]


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
