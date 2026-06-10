"""Small SPARQL lexical helpers used before handing queries to pyoxigraph."""

from __future__ import annotations

import re

_SERVICE_KEYWORD_RE = re.compile(r"(?is)\bSERVICE\b")


def _mask_comments_and_literals(query: str, *, mask_literals: bool) -> str:
    """Replace comments, and optionally string literals, while preserving query length."""
    chars = list(query)
    i = 0
    in_iri = False
    quote: str | None = None
    triple_quote: str | None = None
    escaped = False

    while i < len(chars):
        char = chars[i]
        if quote is not None:
            if mask_literals and char not in {"\n", "\r"}:
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
                if mask_literals:
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
            if mask_literals:
                for offset in range(3):
                    chars[i + offset] = " "
            i += 3
            continue

        if char in {'"', "'"}:
            quote = char
            if mask_literals:
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
    return _mask_comments_and_literals(query, mask_literals=False)


def contains_service_clause(query: str) -> bool:
    """Return true when query code contains a SPARQL SERVICE keyword."""
    masked = _mask_comments_and_literals(query, mask_literals=True)
    return _SERVICE_KEYWORD_RE.search(masked) is not None
