from urllib.parse import quote

RDF_THING_GRAPH_PREFIX = "urn:smart-living-copilot:rdf:thing:"


def thing_graph_iri(thing_id: str) -> str:
    """Return the named graph IRI used to store one Thing Description."""
    return f"{RDF_THING_GRAPH_PREFIX}{quote(thing_id, safe='')}"
