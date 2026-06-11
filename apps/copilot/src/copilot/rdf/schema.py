"""Schema introspection for the local Thing knowledge graph.

Surfaces the **domain** vocabulary actually present in the graph so the agent can draft
valid ``things_sparql`` queries — deliberately excluding the WoT Thing-Description
"plumbing" vocabularies (TD ontology, security schemes, hypermedia controls, data-schema
wiring, and protocol bindings such as HTTP/CoAP/MQTT/Modbus). Those describe TD *mechanics*
(forms, hrefs, securityDefinitions, affordance structure), not the device/place semantics a
question is actually about, and they would otherwise drown the useful terms.
"""

from __future__ import annotations

from typing import Any

# WoT TD plumbing + RDF syntax — structural noise, never domain semantics.
WOT_INFRA_NAMESPACES: tuple[str, ...] = (
    "https://www.w3.org/2019/wot/td#",  # TD ontology (affordances, forms wiring)
    "https://www.w3.org/2019/wot/security#",  # security schemes
    "https://www.w3.org/2019/wot/hypermedia#",  # hctl forms/links
    "https://www.w3.org/2019/wot/json-schema#",  # data-schema wiring
    "http://www.w3.org/2011/http#",  # htv — HTTP binding
    "http://www.w3.org/2011/coap#",  # CoAP binding (legacy ns)
    "https://www.w3.org/2019/wot/coap#",  # cov — CoAP binding
    "https://www.w3.org/2019/wot/mqtt#",  # mqv — MQTT binding
    "https://www.w3.org/2019/wot/modbus#",  # modv — Modbus binding
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",  # rdf: syntax (rdf:type etc.)
)

# Recognised domain ontologies, surfaced as prefixes when present in the graph.
DOMAIN_PREFIXES: dict[str, str] = {
    "saref": "https://saref.etsi.org/core/",
    "s4bldg": "https://saref.etsi.org/saref4bldg/",
    "s4ener": "https://saref.etsi.org/saref4ener/",
    "sosa": "http://www.w3.org/ns/sosa/",
    "ssn": "http://www.w3.org/ns/ssn/",
    "qudt": "http://qudt.org/schema/qudt/",
    "unit": "http://qudt.org/vocab/unit/",
    "om": "http://www.ontology-of-units-of-measure.org/resource/om-2/",
    "brick": "https://brickschema.org/schema/Brick#",
    "schema": "http://schema.org/",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}

CLASSES_QUERY = (
    "SELECT ?class (COUNT(DISTINCT ?s) AS ?count) "
    "WHERE { ?s a ?class } GROUP BY ?class ORDER BY DESC(?count)"
)
PREDICATES_QUERY = (
    "SELECT ?predicate (COUNT(*) AS ?count) "
    "WHERE { ?s ?predicate ?o } GROUP BY ?predicate ORDER BY DESC(?count)"
)

_NOTE = (
    "Domain vocabulary only. WoT Thing-Description plumbing (td:, wotsec:, hctl:, "
    "jsonschema:, and protocol bindings such as htv:) is omitted. Use these terms — as "
    "full <IRI>s or via the listed prefixes — when writing things_sparql queries."
)


def is_domain_iri(iri: str) -> bool:
    """True unless the IRI belongs to a WoT TD plumbing / RDF-syntax namespace."""
    return not any(iri.startswith(namespace) for namespace in WOT_INFRA_NAMESPACES)


def _term_rows(rows: list[Any], variable: str) -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        term = row.get(variable)
        if not isinstance(term, dict) or term.get("type") != "uri":
            continue
        iri = term.get("value")
        if not isinstance(iri, str) or not is_domain_iri(iri):
            continue
        count_binding = row.get("count")
        count: int | None = None
        if isinstance(count_binding, dict):
            try:
                count = int(count_binding.get("value"))
            except (TypeError, ValueError):
                count = None
        terms.append({"iri": iri, "count": count})
    return terms


def summarize_schema(
    *,
    class_rows: list[Any],
    predicate_rows: list[Any],
    limit: int,
) -> dict[str, Any]:
    """Build the domain-only schema summary from raw SELECT result rows."""
    classes = _term_rows(class_rows, "class")[:limit]
    predicates = _term_rows(predicate_rows, "predicate")[:limit]
    present = {item["iri"] for item in (*classes, *predicates)}
    prefixes = {
        prefix: namespace
        for prefix, namespace in DOMAIN_PREFIXES.items()
        if any(iri.startswith(namespace) for iri in present)
    }
    return {
        "classes": classes,
        "predicates": predicates,
        "prefixes": prefixes,
        "note": _NOTE,
    }
