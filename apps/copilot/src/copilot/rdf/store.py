from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyoxigraph import (
    BlankNode,
    DefaultGraph,
    Literal,
    NamedNode,
    Quad,
    QueryBoolean,
    QueryResultsFormat,
    QuerySolutions,
    RdfFormat,
    Store,
)

from copilot.rdf.contexts import expand_cached_jsonld_contexts
from copilot.rdf.iris import thing_graph_iri
from copilot.rdf.sparql_text import contains_service_clause, strip_sparql_comments
from copilot.thing_indexer.summary_utils import clean_text, normalize_thing_td_payload

_READ_ONLY_QUERY_KINDS = {"SELECT", "ASK", "CONSTRUCT", "DESCRIBE"}
_PROLOG_RE = re.compile(r"(?is)^\s*(?:BASE\s+<[^>]*>|PREFIX\s+[^:\s]*:\s*<[^>]*>)\s*")
_QUERY_KIND_RE = re.compile(r"(?is)^([A-Za-z]+)\b")
_GRAPH_RESULT_MAX_BYTES = 200_000


def sparql_query_kind(query: str) -> str:
    """Return the leading SPARQL query form after BASE/PREFIX declarations."""
    remaining = strip_sparql_comments(query).strip()
    while True:
        match = _PROLOG_RE.match(remaining)
        if match is None:
            break
        remaining = remaining[match.end() :].lstrip()

    match = _QUERY_KIND_RE.match(remaining)
    if match is None:
        raise ValueError("SPARQL query must start with SELECT, ASK, CONSTRUCT, or DESCRIBE")

    kind = match.group(1).upper()
    if kind not in _READ_ONLY_QUERY_KINDS:
        raise ValueError("Only read-only SPARQL queries are allowed")
    return kind


def _term_to_compact_binding(term: Any) -> dict[str, Any]:
    if isinstance(term, NamedNode):
        return {"type": "uri", "value": term.value}
    if isinstance(term, BlankNode):
        return {"type": "bnode", "value": term.value}
    if isinstance(term, Literal):
        compact = {"type": "literal", "value": term.value}
        if term.language:
            compact["language"] = term.language
        elif term.datatype:
            compact["datatype"] = term.datatype.value
        return compact
    return {"type": "", "value": str(term)}


def _json_bytes_to_object(value: bytes | str) -> dict[str, Any]:
    payload = value.decode("utf-8") if isinstance(value, bytes) else value
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise ValueError("SPARQL result serialization did not produce a JSON object")
    return decoded


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _triple_to_ntriples_bytes(triple: Any) -> bytes:
    store = Store()
    store.add(Quad(triple.subject, triple.predicate, triple.object))
    serialized = store.dump(format=RdfFormat.N_TRIPLES, from_graph=DefaultGraph())
    if not isinstance(serialized, bytes):
        raise ValueError("SPARQL graph serialization did not produce bytes")
    return serialized


@dataclass(frozen=True)
class RdfReindexResult:
    indexed: int
    failed: int
    errors: list[dict[str, str]]


class RdfStoreService:
    def __init__(self, store_path: str) -> None:
        path = Path(store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._store = Store(str(path))
        self._lock = asyncio.Lock()

    async def process_event(self, event: dict[str, Any]) -> None:
        thing_id = clean_text(event.get("id"))
        event_type = event.get("eventType")
        if not thing_id:
            raise ValueError("Thing RDF event is missing 'id'")

        if event_type == "remove":
            await self.delete_thing(thing_id)
            return
        if event_type not in {"create", "update"}:
            return

        await self.upsert_thing(thing_id, normalize_thing_td_payload(event))

    async def upsert_thing(self, thing_id: str, thing_td: dict[str, Any]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._upsert_thing_sync, thing_id, thing_td)

    async def delete_thing(self, thing_id: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._delete_thing_sync, thing_id)

    async def reindex(self, things: list[tuple[str, dict[str, Any]]]) -> RdfReindexResult:
        async with self._lock:
            return await asyncio.to_thread(self._reindex_sync, things)

    async def query(
        self,
        *,
        query: str,
        limit: int,
        use_default_graph_as_union: bool = True,
    ) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(
                self._query_sync,
                query,
                limit,
                use_default_graph_as_union,
            )

    def _upsert_thing_sync(self, thing_id: str, thing_td: dict[str, Any]) -> None:
        graph_name = NamedNode(thing_graph_iri(thing_id))
        payload = json.dumps(expand_cached_jsonld_contexts(thing_td), ensure_ascii=False)

        parsed_store = Store()
        parsed_store.load(
            input=payload,
            format=RdfFormat.JSON_LD,
            base_iri=thing_id,
        )
        quads = [
            Quad(quad.subject, quad.predicate, quad.object, graph_name) for quad in parsed_store
        ]

        self._store.remove_graph(graph_name)
        if quads:
            self._store.bulk_extend(quads)
        self._store.flush()

    def _delete_thing_sync(self, thing_id: str) -> None:
        self._store.remove_graph(NamedNode(thing_graph_iri(thing_id)))
        self._store.flush()

    def _reindex_sync(self, things: list[tuple[str, dict[str, Any]]]) -> RdfReindexResult:
        parsed_by_graph: list[tuple[NamedNode, list[Quad]]] = []
        errors: list[dict[str, str]] = []
        for thing_id, document in things:
            graph_name = NamedNode(thing_graph_iri(thing_id))
            try:
                payload = json.dumps(expand_cached_jsonld_contexts(document), ensure_ascii=False)
                parsed_store = Store()
                parsed_store.load(
                    input=payload,
                    format=RdfFormat.JSON_LD,
                    base_iri=thing_id,
                )
                parsed_by_graph.append(
                    (
                        graph_name,
                        [
                            Quad(quad.subject, quad.predicate, quad.object, graph_name)
                            for quad in parsed_store
                        ],
                    )
                )
            except Exception as exc:
                errors.append({"thing_id": thing_id, "error": str(exc)})

        self._store.clear()
        for _graph_name, quads in parsed_by_graph:
            if quads:
                self._store.bulk_extend(quads)
        self._store.flush()
        return RdfReindexResult(
            indexed=len(parsed_by_graph),
            failed=len(errors),
            errors=errors,
        )

    def _query_sync(
        self,
        query: str,
        limit: int,
        use_default_graph_as_union: bool,
    ) -> dict[str, Any]:
        kind = sparql_query_kind(query)
        if contains_service_clause(query):
            raise ValueError("SPARQL SERVICE is not supported on the local RDF query endpoint")
        result = self._store.query(
            query,
            use_default_graph_as_union=use_default_graph_as_union,
        )

        if kind == "SELECT":
            if not isinstance(result, QuerySolutions):
                raise ValueError("SPARQL SELECT did not return query solutions")
            variables = [variable.value for variable in result.variables]
            rows = []
            truncated = False
            for index, binding in enumerate(result):
                if index >= limit:
                    truncated = True
                    break
                rows.append(
                    {
                        variable: _term_to_compact_binding(value)
                        for variable in variables
                        if (value := binding[variable]) is not None
                    }
                )
            return {
                "type": "select",
                "query": query,
                "limit": limit,
                "variables": variables,
                "rows": rows,
                "truncated": truncated,
            }

        if kind == "ASK":
            if isinstance(result, QueryBoolean):
                boolean = bool(result)
            else:
                data = _json_bytes_to_object(result.serialize(format=QueryResultsFormat.JSON))
                boolean = bool(data.get("boolean", False))
            return {
                "type": "ask",
                "query": query,
                "limit": limit,
                "boolean": boolean,
                "truncated": False,
            }

        chunks: list[bytes] = []
        total_bytes = 0
        truncated = False
        for index, triple in enumerate(result):
            if index >= limit:
                truncated = True
                break
            chunk = _triple_to_ntriples_bytes(triple)
            if total_bytes + len(chunk) > _GRAPH_RESULT_MAX_BYTES:
                truncated = True
                break
            chunks.append(chunk)
            total_bytes += len(chunk)
        rdf = b"".join(chunks).decode("utf-8")
        return {
            "type": kind.lower(),
            "query": query,
            "limit": limit,
            "format": "application/n-triples",
            "rdf": rdf,
            "truncated": truncated,
        }
