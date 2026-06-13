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
        if quote is not None:
            i, quote, triple_quote, escaped = _consume_quoted_literal(
                chars,
                query,
                i,
                quote=quote,
                triple_quote=triple_quote,
                escaped=escaped,
                mask_literals=mask_literals,
            )
            continue

        i, in_iri, quote, triple_quote = _consume_unquoted(
            chars,
            query,
            i,
            in_iri=in_iri,
            mask_literals=mask_literals,
        )

    return "".join(chars)


def _consume_unquoted(
    chars: list[str],
    query: str,
    i: int,
    *,
    in_iri: bool,
    mask_literals: bool,
) -> tuple[int, bool, str | None, str | None]:
    char = chars[i]
    if in_iri:
        return i + 1, char != ">", None, None
    if char == "<":
        return i + 1, True, None, None
    if query.startswith('"""', i) or query.startswith("'''", i):
        triple_quote = query[i : i + 3]
        if mask_literals:
            _mask_chars(chars, i, 3)
        return i + 3, False, query[i], triple_quote
    if char in {'"', "'"}:
        if mask_literals:
            chars[i] = " "
        return i + 1, False, char, None
    if char == "#":
        return _consume_comment(chars, i), False, None, None
    return i + 1, False, None, None


def _consume_quoted_literal(
    chars: list[str],
    query: str,
    i: int,
    *,
    quote: str,
    triple_quote: str | None,
    escaped: bool,
    mask_literals: bool,
) -> tuple[int, str | None, str | None, bool]:
    char = chars[i]
    if mask_literals and char not in {"\n", "\r"}:
        chars[i] = " "
    if escaped:
        return i + 1, quote, triple_quote, False
    if char == "\\":
        return i + 1, quote, triple_quote, True
    if triple_quote is not None and query.startswith(triple_quote, i):
        if mask_literals:
            _mask_chars(chars, i, 3)
        return i + 3, None, None, False
    if triple_quote is None and char == quote:
        return i + 1, None, None, False
    return i + 1, quote, triple_quote, False


def _consume_comment(chars: list[str], i: int) -> int:
    while i < len(chars) and chars[i] not in {"\n", "\r"}:
        chars[i] = " "
        i += 1
    return i


def _mask_chars(chars: list[str], start: int, length: int) -> None:
    for offset in range(length):
        chars[start + offset] = " "


def strip_sparql_comments(query: str) -> str:
    """Replace SPARQL comments with spaces while preserving string/IRI content."""
    return _mask_comments_and_literals(query, mask_literals=False)


def contains_service_clause(query: str) -> bool:
    """Return true when query code contains a SPARQL SERVICE keyword."""
    masked = _mask_comments_and_literals(query, mask_literals=True)
    return _SERVICE_KEYWORD_RE.search(masked) is not None
