from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from wotbot.discovery.models import CandidateDraft, SearchIntent, SourceDefinition

_WORD = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_QUOTED = re.compile(r"[\"“”']([^\"“”']{2,80})[\"“”']")
_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "all",
        "an",
        "and",
        "available",
        "data",
        "dataset",
        "datasets",
        "der",
        "die",
        "ein",
        "eine",
        "et",
        "everything",
        "find",
        "for",
        "from",
        "für",
        "in",
        "la",
        "le",
        "les",
        "mit",
        "of",
        "on",
        "open",
        "or",
        "please",
        "public",
        "search",
        "show",
        "the",
        "to",
        "und",
        "valid",
        "von",
        "with",
        "zu",
    }
)


def prepare_search_intent(query: str, source: SourceDefinition) -> SearchIntent:
    """Extract stable search terms while removing source-level repetition."""

    original = " ".join(unicodedata.normalize("NFKC", query).split())
    tokens = _unique(_words(original))
    content = [token for token in tokens if token.casefold() not in _STOPWORDS]

    source_terms = {
        token.casefold()
        for token in _words(" ".join((source.title, *source.tags)))
        if token.casefold() not in _STOPWORDS
    }
    without_source = [token for token in content if token.casefold() not in source_terms]
    if without_source:
        content = without_source

    quoted = [match.group(1).strip() for match in _QUOTED.finditer(original)]
    entities = _unique(
        [
            *quoted,
            *(
                token
                for token in content
                if _looks_like_entity(token) and token.casefold() not in source_terms
            ),
        ]
    )[:4]
    return SearchIntent(
        original=original,
        entities=tuple(entities),
        keywords=tuple(content[:12]),
    )


def rank_candidates(
    intent: SearchIntent,
    candidates: Iterable[tuple[CandidateDraft, str]],
    *,
    limit: int,
    require_match: bool,
) -> list[CandidateDraft]:
    """Rank bounded provider results against the unabridged original intent."""

    ranked: list[tuple[int, int, CandidateDraft]] = []
    for index, (candidate, search_text) in enumerate(candidates):
        score = relevance_score(intent, candidate.title, search_text)
        if require_match and intent.terms and score == 0:
            continue
        ranked.append((score, index, candidate))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [candidate for _score, _index, candidate in ranked[:limit]]


def relevance_score(intent: SearchIntent, title: str, search_text: str) -> int:
    if not intent.terms:
        return 1

    normalized_title = _normalized(title)
    normalized_text = _normalized(search_text)
    title_words = {word.casefold() for word in _words(title)}
    text_words = {word.casefold() for word in _words(search_text)}
    score = 0
    matched_keywords = 0

    for entity in intent.entities:
        normalized_entity = _normalized(entity)
        if normalized_entity and normalized_entity in normalized_title:
            score += 20
        elif normalized_entity and normalized_entity in normalized_text:
            score += 10

    for keyword in intent.keywords:
        folded = keyword.casefold()
        if folded in title_words:
            score += 6
            matched_keywords += 1
        elif folded in text_words:
            score += 2
            matched_keywords += 1

    if intent.keywords and matched_keywords == len(intent.keywords):
        score += 5
    if _normalized(intent.original) in normalized_text:
        score += 5
    return score


def _words(value: str) -> list[str]:
    return _WORD.findall(value)


def _normalized(value: str) -> str:
    return " ".join(word.casefold() for word in _words(value))


def _looks_like_entity(token: str) -> bool:
    letters = [character for character in token if character.isalpha()]
    return bool(letters) and (
        (len(letters) > 1 and all(character.isupper() for character in letters))
        or any(character.isupper() for character in token[1:])
    )


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.casefold()
        if not value or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return result
