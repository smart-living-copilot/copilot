from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from copilot.catalog.enrichment.config import EnrichmentConfig, load_term_payload


class VocabularyTerm(BaseModel):
    label: str
    iri: str
    kind: str = "class"
    aliases: list[str] = []


@dataclass(frozen=True)
class Vocabulary:
    prefixes: dict[str, str]
    descriptions: dict[str, str]
    terms: tuple[VocabularyTerm, ...]
    terms_by_iri: frozenset[str]

    def expand(self, value: str) -> str:
        if value.startswith(("http://", "https://")):
            return value
        if ":" not in value:
            return value
        prefix, suffix = value.split(":", 1)
        namespace = self.prefixes.get(prefix)
        if namespace is None:
            return value
        return f"{namespace}{suffix}"

    def compact(self, iri: str) -> str:
        for prefix, namespace in sorted(
            self.prefixes.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        ):
            if iri.startswith(namespace):
                return f"{prefix}:{iri.removeprefix(namespace)}"
        return iri

    def contains(self, value: str) -> bool:
        return self.expand(value) in self.terms_by_iri

    def prompt_terms(self, *, limit: int = 160) -> str:
        rows = []
        for term in self.terms[:limit]:
            aliases = f" aliases={', '.join(term.aliases)}" if term.aliases else ""
            rows.append(f"- {term.kind}: {term.label} -> {term.iri}{aliases}")
        if len(self.terms) > limit:
            rows.append(f"- ... {len(self.terms) - limit} more configured terms omitted")
        return "\n".join(rows)


def build_vocabulary(config: EnrichmentConfig, *, config_path: str = "") -> Vocabulary:
    prefixes: dict[str, str] = {}
    descriptions: dict[str, str] = {}
    terms: list[VocabularyTerm] = []

    for ontology in config.ontologies:
        prefixes[ontology.prefix] = ontology.namespace
        descriptions[ontology.prefix] = ontology.description
        for item in load_term_payload(ontology.terms, config_path=config_path):
            term = VocabularyTerm.model_validate(item)
            terms.append(term)

    return Vocabulary(
        prefixes=prefixes,
        descriptions=descriptions,
        terms=tuple(terms),
        terms_by_iri=frozenset(term.iri for term in terms),
    )


@lru_cache(maxsize=8)
def build_cached_vocabulary(config_json: str, *, config_path: str = "") -> Vocabulary:
    config = EnrichmentConfig.model_validate_json(config_json)
    return build_vocabulary(config, config_path=config_path)


def unknown_proposal_iris(proposal: Any, vocabulary: Vocabulary) -> list[str]:
    from copilot.catalog.enrichment.models import EnrichmentProposal

    parsed = EnrichmentProposal.model_validate(proposal)
    emitted: list[str] = []
    emitted.extend(parsed.thing_types)
    for affordance in parsed.affordances:
        emitted.extend(affordance.types)
        if affordance.unit_iri:
            emitted.append(affordance.unit_iri)

    unknown = sorted({value for value in emitted if not vocabulary.contains(value)})
    return unknown
