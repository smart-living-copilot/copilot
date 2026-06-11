from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage

from copilot.catalog.enrichment.config import EnrichmentConfig
from copilot.catalog.enrichment.models import (
    AffordanceAnnotation,
    EnrichmentDiffItem,
    EnrichmentProposal,
    EnrichmentResult,
    EnrichmentValidation,
)
from copilot.catalog.enrichment.vocab import (
    Vocabulary,
    build_cached_vocabulary,
    unknown_proposal_iris,
)
from copilot.catalog.validation import validate_document


class EnrichmentError(RuntimeError):
    def __init__(self, message: str, *, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


async def enrich_thing_document(
    document: dict[str, Any],
    *,
    config: EnrichmentConfig,
    llm: Any,
    max_repair_attempts: int = 2,
) -> EnrichmentResult:
    try:
        sanitized = validate_document(document)
    except HTTPException:
        raise
    vocabulary = build_cached_vocabulary(config.model_dump_json())
    structured_llm = llm.with_structured_output(EnrichmentProposal)

    errors: list[str] = []
    max_attempts = max(1, max_repair_attempts + 1)
    for attempt in range(1, max_attempts + 1):
        proposal = await _invoke_proposal(
            structured_llm,
            document=sanitized,
            config=config,
            vocabulary=vocabulary,
            errors=errors,
        )
        unknown = unknown_proposal_iris(proposal, vocabulary)
        if unknown:
            errors = [f"Unknown semantic IRI: {iri}" for iri in unknown]
            continue

        enriched, diff = merge_enrichment(sanitized, proposal, vocabulary=vocabulary)
        try:
            validated = validate_document(enriched)
        except HTTPException as exc:
            errors = [f"Enriched TD failed validation: {exc.detail}"]
            continue

        return EnrichmentResult(
            enriched=validated,
            diff=diff,
            validation=EnrichmentValidation(ok=True, attempts=attempt),
        )

    raise EnrichmentError("Unable to produce a valid enrichment proposal", errors=errors)


def merge_enrichment(
    document: dict[str, Any],
    proposal: EnrichmentProposal,
    *,
    vocabulary: Vocabulary,
) -> tuple[dict[str, Any], list[EnrichmentDiffItem]]:
    enriched = deepcopy(document)
    diff: list[EnrichmentDiffItem] = []

    _ensure_context_prefixes(enriched, vocabulary=vocabulary, diff=diff)

    for iri in proposal.thing_types:
        _add_type(
            enriched,
            vocabulary.compact(vocabulary.expand(iri)),
            path="@type",
            diff=diff,
            label="Thing type",
        )

    for annotation in proposal.affordances:
        _merge_affordance(enriched, annotation, vocabulary=vocabulary, diff=diff)

    return enriched, diff


async def _invoke_proposal(
    structured_llm: Any,
    *,
    document: dict[str, Any],
    config: EnrichmentConfig,
    vocabulary: Vocabulary,
    errors: list[str],
) -> EnrichmentProposal:
    repair = ""
    if errors:
        repair = "\nRepair these validation errors from the previous proposal:\n" + "\n".join(
            f"- {error}" for error in errors
        )

    response = await structured_llm.ainvoke(
        [
            SystemMessage(content=_system_prompt(config, vocabulary)),
            HumanMessage(content=f"Thing Description JSON:\n{document!r}{repair}"),
        ]
    )
    return EnrichmentProposal.model_validate(response)


def _system_prompt(config: EnrichmentConfig, vocabulary: Vocabulary) -> str:
    return (
        "You enrich W3C Thing Descriptions with semantic annotations.\n"
        "Return only the structured annotation proposal. Do not rewrite the TD.\n"
        "Use only IRIs from the allowed vocabulary. Prefer full IRIs in the proposal.\n"
        "Suggest additive annotations only: Thing @type, affordance @type, and QUDT units "
        "for numeric properties.\n"
        f"{config.system_prompt_extra}\n\n"
        f"Allowed vocabulary:\n{vocabulary.prompt_terms()}"
    )


def _ensure_context_prefixes(
    document: dict[str, Any],
    *,
    vocabulary: Vocabulary,
    diff: list[EnrichmentDiffItem],
) -> None:
    context = document.get("@context")
    if isinstance(context, list):
        context_items = context
    elif context is None:
        context_items = []
        document["@context"] = context_items
    else:
        context_items = [context]
        document["@context"] = context_items

    prefix_map = _find_context_prefix_map(context_items)
    if prefix_map is None:
        prefix_map = {}
        context_items.append(prefix_map)

    for prefix, namespace in vocabulary.prefixes.items():
        if prefix_map.get(prefix) == namespace:
            continue
        if prefix in prefix_map:
            continue
        prefix_map[prefix] = namespace
        diff.append(
            EnrichmentDiffItem(
                kind="prefix",
                path=f"@context.{prefix}",
                value=namespace,
                label=f"Prefix {prefix}",
            )
        )


def _find_context_prefix_map(context_items: list[Any]) -> dict[str, Any] | None:
    for item in context_items:
        if isinstance(item, dict):
            return item
    return None


def _merge_affordance(
    document: dict[str, Any],
    annotation: AffordanceAnnotation,
    *,
    vocabulary: Vocabulary,
    diff: list[EnrichmentDiffItem],
) -> None:
    section = document.get(annotation.section)
    if not isinstance(section, dict):
        return
    target = section.get(annotation.name)
    if not isinstance(target, dict):
        return

    for iri in annotation.types:
        _add_type(
            target,
            vocabulary.compact(vocabulary.expand(iri)),
            path=f"{annotation.section}.{annotation.name}.@type",
            diff=diff,
            label=f"{annotation.name} type",
        )

    if (
        annotation.section == "properties"
        and annotation.unit_iri
        and _is_numeric_schema(target)
        and "qudt:unit" not in target
    ):
        value = {"@id": vocabulary.compact(vocabulary.expand(annotation.unit_iri))}
        target["qudt:unit"] = value
        diff.append(
            EnrichmentDiffItem(
                kind="unit",
                path=f"properties.{annotation.name}.qudt:unit",
                value=value,
                label=f"{annotation.name} unit",
            )
        )


def _add_type(
    target: dict[str, Any],
    value: str,
    *,
    path: str,
    diff: list[EnrichmentDiffItem],
    label: str,
) -> None:
    current = target.get("@type")
    if current is None:
        target["@type"] = value
    elif isinstance(current, list):
        if value in current:
            return
        current.append(value)
    elif current == value:
        return
    else:
        target["@type"] = [current, value]

    diff.append(EnrichmentDiffItem(kind="type", path=path, value=value, label=label))


def _is_numeric_schema(schema: dict[str, Any]) -> bool:
    schema_type = schema.get("type")
    if schema_type in {"number", "integer"}:
        return True
    if isinstance(schema_type, list) and {"number", "integer"} & set(schema_type):
        return True
    return False
