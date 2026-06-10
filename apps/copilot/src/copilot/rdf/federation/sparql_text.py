"""SPARQL text handling: comment/string masking, SERVICE rewriting, and join diagnostics.

These functions operate on raw query text (no real parser). Everything that masks the
query is **exactly length-preserving** so that offsets computed on the masked copy can be
applied to the original — `rewrite_federated_query` depends on that invariant.
"""

from __future__ import annotations

import re

_SERVICE_IRI_RE = re.compile(r"(?is)\bSERVICE\s+(?:SILENT\s+)?<([^>]*)>")
_SERVICE_KEYWORD_RE = re.compile(r"(?is)\bSERVICE\b")
_SERVICE_TARGET_ERROR = (
    "SPARQL SERVICE targets must be declared endpoint Thing ids passed in endpoints"
)
_SPARQL_VAR_RE = re.compile(r"[$?][A-Za-z_][A-Za-z0-9_]*")
_SERVICE_CONSTRAINT_RE = re.compile(r"(?is)\b(?:VALUES|FILTER|BIND)\b")


def _mask_sparql_non_code(query: str, *, mask_strings: bool) -> str:
    chars = list(query)
    i = 0
    in_iri = False
    quote: str | None = None
    triple_quote: str | None = None
    escaped = False

    while i < len(chars):
        char = chars[i]
        if quote is not None:
            if mask_strings and char not in {"\n", "\r"}:
                chars[i] = " "
            if escaped:
                escaped = False
                i += 1
                continue
            if char == "\\":
                escaped = True
                i += 1
                continue
            if triple_quote is not None and query.startswith(triple_quote, i):
                if mask_strings:
                    for offset in range(3):
                        chars[i + offset] = " "
                i += 3
                quote = None
                triple_quote = None
                continue
            if triple_quote is None and char == quote:
                quote = None
            i += 1
            continue

        if in_iri:
            if char == ">":
                in_iri = False
            i += 1
            continue

        if char == "<":
            in_iri = True
            i += 1
            continue

        if query.startswith('"""', i) or query.startswith("'''", i):
            triple_quote = query[i : i + 3]
            quote = query[i]
            if mask_strings:
                for offset in range(3):
                    chars[i + offset] = " "
            i += 3
            continue

        if char in {'"', "'"}:
            quote = char
            if mask_strings:
                chars[i] = " "
            i += 1
            continue

        if char == "#":
            while i < len(chars) and chars[i] not in {"\n", "\r"}:
                chars[i] = " "
                i += 1
            continue

        i += 1

    return "".join(chars)


def strip_sparql_comments(query: str) -> str:
    """Replace SPARQL comments with spaces while preserving string/IRI content."""
    return _mask_sparql_non_code(query, mask_strings=False)


def _mask_sparql_strings_and_comments(query: str) -> str:
    return _mask_sparql_non_code(query, mask_strings=True)


def service_iris(query: str) -> list[str]:
    stripped = _mask_sparql_strings_and_comments(query)
    return [match.group(1) for match in _SERVICE_IRI_RE.finditer(stripped)]


def _balanced_block_end(query: str, open_brace_index: int) -> int | None:
    depth = 0
    for index in range(open_brace_index, len(query)):
        char = query[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _sparql_variables(query: str) -> set[str]:
    return {match.group(0) for match in _SPARQL_VAR_RE.finditer(query)}


def service_constraint_diagnostics(query: str) -> list[dict[str, str]]:
    """Warn when SERVICE joins rely on outer binding pushdown."""
    stripped = _mask_sparql_strings_and_comments(query)
    where_match = re.search(r"(?is)\bWHERE\s*{", stripped)
    where_body_start = where_match.end() - 1 if where_match else stripped.find("{")
    if where_body_start < 0:
        where_body_start = 0

    diagnostics: list[dict[str, str]] = []
    for match in _SERVICE_IRI_RE.finditer(stripped):
        open_brace_index = stripped.find("{", match.end())
        if open_brace_index < 0:
            continue
        close_brace_index = _balanced_block_end(stripped, open_brace_index)
        if close_brace_index is None:
            continue

        service_body = stripped[open_brace_index + 1 : close_brace_index]
        if _SERVICE_CONSTRAINT_RE.search(service_body):
            continue

        outer_body = (
            stripped[where_body_start : match.start()] + stripped[close_brace_index + 1 :]
        )
        shared_variables = _sparql_variables(service_body).intersection(
            _sparql_variables(outer_body)
        )
        if not shared_variables:
            continue

        diagnostics.append(
            {
                "code": "service-unbounded-join",
                "service_iri": match.group(1),
                "message": (
                    "SERVICE block shares variables with outer graph patterns but has no "
                    "inner VALUES, FILTER, or BIND constraint; outer bindings are not "
                    "pushed into SERVICE."
                ),
            }
        )
    return diagnostics


def rewrite_federated_query(query: str, service_rewrites: dict[str, str] | None = None) -> str:
    rewrites = service_rewrites or {}
    stripped = _mask_sparql_strings_and_comments(query)
    # Offsets are computed on the masked copy and applied to the original; this only holds
    # because masking replaces characters in place and is exactly length-preserving.
    assert len(stripped) == len(query)

    pieces: list[str] = []
    last = 0
    # Walk every SERVICE keyword (not just the ones with literal IRIs): a SERVICE whose
    # target is a variable or anything other than a declared endpoint-Thing id is rejected,
    # so oxigraph can never be steered at a host that bypasses the proxy.
    for keyword in _SERVICE_KEYWORD_RE.finditer(stripped):
        target = _SERVICE_IRI_RE.match(stripped, keyword.start())
        replacement = rewrites.get(target.group(1)) if target is not None else None
        if not replacement:
            raise ValueError(_SERVICE_TARGET_ERROR)
        pieces.append(query[last : target.start(1)])
        pieces.append(replacement)
        last = target.end(1)

    if not pieces:
        return query
    pieces.append(query[last:])
    return "".join(pieces)
