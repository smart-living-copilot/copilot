from __future__ import annotations

import pytest

from copilot.catalog.enrichment.config import load_enrichment_config
from copilot.catalog.enrichment.models import EnrichmentProposal
from copilot.catalog.enrichment.service import (
    EnrichmentError,
    enrich_thing_document,
    merge_enrichment,
)
from copilot.catalog.enrichment.vocab import build_vocabulary, unknown_proposal_iris


def sample_thing() -> dict[str, object]:
    return {
        "@context": "https://www.w3.org/2022/wot/td/v1.1",
        "id": "urn:thing:alpha",
        "title": "Alpha temperature sensor",
        "securityDefinitions": {"nosec_sc": {"scheme": "nosec"}},
        "security": "nosec_sc",
        "properties": {
            "temperature": {
                "type": "number",
                "unit": "°C",
                "readOnly": True,
                "forms": [{"href": "https://example.test/temp"}],
            }
        },
    }


class FakeStructuredLlm:
    def __init__(self, proposals):
        self.proposals = list(proposals)
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        return self.proposals.pop(0)


class FakeLlm:
    def __init__(self, proposals):
        self.structured = FakeStructuredLlm(proposals)

    def with_structured_output(self, _schema):
        return self.structured


def test_vocabulary_config_loads_packaged_terms_and_rejects_unknown_iris():
    config = load_enrichment_config()
    vocab = build_vocabulary(config)

    assert vocab.contains("saref:TemperatureSensor")
    assert vocab.contains("s4ehaw:TimeSeriesMeasurement")
    assert vocab.contains("https://saref.etsi.org/saref4envi/FrequencyMeasurement")
    assert vocab.contains("http://qudt.org/vocab/unit/DEG_C")
    assert vocab.contains("unit:HZ")

    proposal = EnrichmentProposal(
        thing_types=["https://saref.etsi.org/core/DefinitelyNotARealTerm"]
    )
    assert unknown_proposal_iris(proposal, vocab) == [
        "https://saref.etsi.org/core/DefinitelyNotARealTerm"
    ]


def test_merge_adds_context_types_units_and_preserves_existing_annotations():
    config = load_enrichment_config()
    vocab = build_vocabulary(config)
    document = sample_thing()
    document["@type"] = "saref:Device"

    proposal = EnrichmentProposal(
        thing_types=["https://saref.etsi.org/core/TemperatureSensor"],
        affordances=[
            {
                "section": "properties",
                "name": "temperature",
                "types": ["https://saref.etsi.org/core/Temperature"],
                "unit_iri": "http://qudt.org/vocab/unit/DEG_C",
            }
        ],
    )

    enriched, diff = merge_enrichment(document, proposal, vocabulary=vocab)

    assert enriched["@type"] == ["saref:Device", "saref:TemperatureSensor"]
    temperature = enriched["properties"]["temperature"]
    assert temperature["@type"] == "saref:Temperature"
    assert temperature["qudt:unit"] == {"@id": "unit:DEG_C"}
    assert {item.kind for item in diff} == {"prefix", "type", "unit"}

    enriched_again, diff_again = merge_enrichment(enriched, proposal, vocabulary=vocab)
    assert enriched_again == enriched
    assert [item for item in diff_again if item.kind != "prefix"] == []


@pytest.mark.anyio
async def test_enrich_repairs_unknown_iri_and_returns_valid_diff():
    config = load_enrichment_config()
    bad = EnrichmentProposal(
        thing_types=["https://saref.etsi.org/core/TempSensor"],
    )
    good = EnrichmentProposal(
        thing_types=["https://saref.etsi.org/core/TemperatureSensor"],
        affordances=[
            {
                "section": "properties",
                "name": "temperature",
                "types": ["https://saref.etsi.org/core/Temperature"],
                "unit_iri": "http://qudt.org/vocab/unit/DEG_C",
            }
        ],
    )
    llm = FakeLlm([bad, good])

    result = await enrich_thing_document(
        sample_thing(),
        config=config,
        llm=llm,
        max_repair_attempts=1,
    )

    assert result.validation.ok is True
    assert result.validation.attempts == 2
    assert llm.structured.calls == 2
    assert result.enriched["@type"] == "saref:TemperatureSensor"
    assert any(item.kind == "unit" for item in result.diff)


@pytest.mark.anyio
async def test_enrich_fails_after_repair_budget():
    config = load_enrichment_config()
    bad = EnrichmentProposal(
        thing_types=["https://saref.etsi.org/core/TempSensor"],
    )

    with pytest.raises(EnrichmentError) as exc_info:
        await enrich_thing_document(
            sample_thing(),
            config=config,
            llm=FakeLlm([bad]),
            max_repair_attempts=0,
        )

    assert "Unknown semantic IRI" in exc_info.value.errors[0]
