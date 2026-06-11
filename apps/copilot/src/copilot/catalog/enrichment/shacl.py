from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from pyshacl import validate
from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from copilot.catalog.enrichment.models import ShaclFinding
from copilot.rdf.contexts import expand_cached_jsonld_contexts

SH = "http://www.w3.org/ns/shacl#"
TD = "https://www.w3.org/2019/wot/td#"


def validate_enriched_document(
    document: dict[str, Any],
    *,
    shapes_path: str = "",
) -> tuple[bool, list[ShaclFinding]]:
    data_graph = document_to_graph(document)
    shapes_graph = Graph()
    shapes_graph.parse(data=_shapes_text(shapes_path), format="turtle")

    conforms, results_graph, _results_text = validate(
        data_graph,
        shacl_graph=shapes_graph,
        data_graph_format="turtle",
        shacl_graph_format="turtle",
        inference="none",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
        meta_shacl=False,
        advanced=True,
    )
    findings = _findings_from_report(results_graph, data_graph=data_graph)
    blocking = [finding for finding in findings if finding.blocks_enrichment]
    return bool(conforms) and not blocking, findings


def document_to_graph(document: dict[str, Any]) -> Graph:
    expanded = expand_cached_jsonld_contexts(document)
    graph = Graph()
    graph.parse(data=json.dumps(expanded), format="json-ld")
    return graph


@lru_cache(maxsize=8)
def _shapes_text(shapes_path: str = "") -> str:
    """Load SHACL shapes from an external path, or the packaged default."""
    if shapes_path:
        return Path(shapes_path).read_text(encoding="utf-8")
    root = resources.files("copilot.catalog.enrichment.data")
    return (root / "shapes" / "td-enrichment.ttl").read_text(encoding="utf-8")


def _findings_from_report(results_graph: Graph, *, data_graph: Graph) -> list[ShaclFinding]:
    result_class = URIRef(f"{SH}ValidationResult")
    severity_pred = URIRef(f"{SH}resultSeverity")
    message_pred = URIRef(f"{SH}resultMessage")
    focus_pred = URIRef(f"{SH}focusNode")
    path_pred = URIRef(f"{SH}resultPath")
    source_shape_pred = URIRef(f"{SH}sourceShape")

    findings: list[ShaclFinding] = []
    for result in results_graph.subjects(RDF.type, result_class):
        focus = results_graph.value(result, focus_pred)
        findings.append(
            ShaclFinding(
                severity=_term(results_graph.value(result, severity_pred)),
                message=_term(results_graph.value(result, message_pred)),
                focus_node=_term(focus),
                focus_label=_focus_label(data_graph, focus),
                result_path=_term(results_graph.value(result, path_pred)),
                source_shape=_term(results_graph.value(result, source_shape_pred)),
            )
        )
    return findings


def _term(value: Any) -> str:
    return "" if value is None else str(value)


def _focus_label(data_graph: Graph, focus: Any) -> str:
    if focus is None:
        return ""
    name = data_graph.value(focus, URIRef(f"{TD}name"))
    if name is not None:
        return str(name)
    title = data_graph.value(focus, URIRef(f"{TD}title"))
    if title is not None:
        return str(title)
    return ""
