from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from wotbot.catalog.enrichment.config import EnrichmentConfig, load_term_payload


class VocabularyTerm(BaseModel):
    label: str
    iri: str
    kind: str = "class"
    aliases: list[str] = []
    # For measurement classes: the QUDT unit to fall back to when a TD annotates
    # this measurement but provides no unit. May be a prefixed or full IRI.
    default_unit: str = ""


@dataclass(frozen=True)
class Vocabulary:
    prefixes: dict[str, str]
    descriptions: dict[str, str]
    terms: tuple[VocabularyTerm, ...]
    terms_by_iri: frozenset[str]
    default_units_by_iri: dict[str, str]
    unit_predicate_iri: str

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

    def default_unit_iri(self, class_value: str) -> str | None:
        """Default QUDT unit IRI configured for a measurement class, if any."""
        return self.default_units_by_iri.get(self.expand(class_value))

    def measurement_classes_requiring_unit(self) -> frozenset[str]:
        """Class IRIs that declare a default unit (i.e. are unit-bearing measurements)."""
        return frozenset(self.default_units_by_iri)

    def unit_predicate(self) -> str:
        """Compact form of the predicate that attaches a unit to a property."""
        return self.compact(self.unit_predicate_iri) if self.unit_predicate_iri else ""

    def measurement_unit_defaults(self) -> list[tuple[str, str]]:
        """(label, default unit IRI) for each unit-bearing measurement class."""
        return [
            (term.label, self.expand(term.default_unit)) for term in self.terms if term.default_unit
        ]

    def unit_iri_for_label(self, value: str) -> str | None:
        needle = _normalize_label(value)
        if not needle:
            return None
        for term in self.terms:
            if term.kind != "unit":
                continue
            labels = [term.label, *term.aliases, self.compact(term.iri), term.iri]
            if any(_normalize_label(label) == needle for label in labels):
                return term.iri
        return None

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

    unit_predicate_iri = ""
    for ontology in config.ontologies:
        prefixes[ontology.prefix] = ontology.namespace
        descriptions[ontology.prefix] = ontology.description
        is_unit_ontology = "property_unit" in ontology.use_for
        for item in load_term_payload(ontology.terms, config_path=config_path):
            term = VocabularyTerm.model_validate(item)
            terms.append(term)
            # The predicate that links a property to its unit is the property-kind
            # term in an ontology marked use_for "property_unit" (e.g. qudt:unit).
            if is_unit_ontology and term.kind == "property" and not unit_predicate_iri:
                unit_predicate_iri = term.iri

    def _expand(value: str) -> str:
        if value.startswith(("http://", "https://")) or ":" not in value:
            return value
        prefix, suffix = value.split(":", 1)
        namespace = prefixes.get(prefix)
        return f"{namespace}{suffix}" if namespace else value

    default_units_by_iri = {
        term.iri: _expand(term.default_unit) for term in terms if term.default_unit
    }

    return Vocabulary(
        prefixes=prefixes,
        descriptions=descriptions,
        terms=tuple(terms),
        terms_by_iri=frozenset(term.iri for term in terms),
        default_units_by_iri=default_units_by_iri,
        unit_predicate_iri=unit_predicate_iri,
    )


@lru_cache(maxsize=8)
def build_cached_vocabulary(config_json: str, *, config_path: str = "") -> Vocabulary:
    config = EnrichmentConfig.model_validate_json(config_json)
    return build_vocabulary(config, config_path=config_path)


def unknown_proposal_iris(proposal: Any, vocabulary: Vocabulary) -> list[str]:
    from wotbot.catalog.enrichment.models import EnrichmentProposal

    parsed = EnrichmentProposal.model_validate(proposal)
    emitted: list[str] = []
    emitted.extend(parsed.thing_types)
    for affordance in parsed.affordances:
        emitted.extend(affordance.types)
        if affordance.unit_iri:
            emitted.append(affordance.unit_iri)

    unknown = sorted({value for value in emitted if not vocabulary.contains(value)})
    return unknown


def _normalize_label(value: str) -> str:
    return value.strip().casefold().replace(" ", "").replace("_", "").replace("-", "")
