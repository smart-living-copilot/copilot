from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from pyoxigraph import NamedNode, Quad, QueryResultsFormat, RdfFormat, Store

from copilot.rdf.iris import thing_graph_iri
from copilot.thing_indexer.summary_utils import clean_text, normalize_thing_td_payload

_READ_ONLY_QUERY_KINDS = {"SELECT", "ASK", "CONSTRUCT", "DESCRIBE"}
_COMMENT_RE = re.compile(r"(?m)#.*$")
_PROLOG_RE = re.compile(r"(?is)^\s*(?:BASE\s+<[^>]*>|PREFIX\s+[^:\s]*:\s*<[^>]*>)\s*")
_QUERY_KIND_RE = re.compile(r"(?is)^([A-Za-z]+)\b")


def sparql_query_kind(query: str) -> str:
    """Return the leading SPARQL query form after BASE/PREFIX declarations."""
    remaining = _COMMENT_RE.sub("", query).strip()
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


def _compact_binding(binding: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {
        "type": binding.get("type", ""),
        "value": binding.get("value", ""),
    }
    datatype = binding.get("datatype")
    if isinstance(datatype, str) and datatype:
        compact["datatype"] = datatype
    language = binding.get("xml:lang")
    if isinstance(language, str) and language:
        compact["language"] = language
    return compact


def _json_bytes_to_object(value: bytes | str) -> dict[str, Any]:
    payload = value.decode("utf-8") if isinstance(value, bytes) else value
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise ValueError("SPARQL result serialization did not produce a JSON object")
    return decoded


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

    async def reindex(self, things: list[tuple[str, dict[str, Any]]]) -> int:
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
        payload = json.dumps(thing_td, ensure_ascii=False)

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

    def _reindex_sync(self, things: list[tuple[str, dict[str, Any]]]) -> int:
        parsed_by_graph: list[tuple[NamedNode, list[Quad]]] = []
        for thing_id, document in things:
            graph_name = NamedNode(thing_graph_iri(thing_id))
            payload = json.dumps(document, ensure_ascii=False)
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

        self._store.clear()
        for _graph_name, quads in parsed_by_graph:
            if quads:
                self._store.bulk_extend(quads)
        self._store.flush()
        return len(parsed_by_graph)

    def _query_sync(
        self,
        query: str,
        limit: int,
        use_default_graph_as_union: bool,
    ) -> dict[str, Any]:
        kind = sparql_query_kind(query)
        result = self._store.query(
            query,
            use_default_graph_as_union=use_default_graph_as_union,
        )

        if kind == "SELECT":
            data = _json_bytes_to_object(result.serialize(format=QueryResultsFormat.JSON))
            variables = [str(item) for item in data.get("head", {}).get("vars", [])]
            bindings = data.get("results", {}).get("bindings", [])
            if not isinstance(bindings, list):
                bindings = []
            rows = []
            for binding in bindings[:limit]:
                if not isinstance(binding, dict):
                    continue
                rows.append(
                    {
                        variable: _compact_binding(value)
                        for variable, value in binding.items()
                        if isinstance(variable, str) and isinstance(value, dict)
                    }
                )
            return {
                "type": "select",
                "query": query,
                "limit": limit,
                "variables": variables,
                "rows": rows,
                "truncated": len(bindings) > limit,
            }

        if kind == "ASK":
            data = _json_bytes_to_object(result.serialize(format=QueryResultsFormat.JSON))
            return {
                "type": "ask",
                "query": query,
                "limit": limit,
                "boolean": bool(data.get("boolean", False)),
                "truncated": False,
            }

        serialized = result.serialize(format=RdfFormat.N_TRIPLES)
        rdf = serialized.decode("utf-8") if isinstance(serialized, bytes) else serialized
        return {
            "type": kind.lower(),
            "query": query,
            "limit": limit,
            "format": "application/n-triples",
            "rdf": rdf,
            "truncated": False,
        }
