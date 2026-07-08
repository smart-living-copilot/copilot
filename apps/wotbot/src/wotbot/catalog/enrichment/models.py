from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AffordanceSection = Literal["properties", "actions", "events"]
DiffKind = Literal["prefix", "type", "unit"]


class AffordanceAnnotation(BaseModel):
    section: AffordanceSection
    name: str
    types: list[str] = Field(default_factory=list)
    unit_iri: str | None = None
    rationale: str = ""


class EnrichmentProposal(BaseModel):
    thing_types: list[str] = Field(default_factory=list)
    thing_rationale: str = ""
    affordances: list[AffordanceAnnotation] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class EnrichmentDiffItem(BaseModel):
    kind: DiffKind
    path: str
    value: Any
    label: str
    rationale: str = ""


class ShaclFinding(BaseModel):
    severity: str
    message: str
    focus_node: str = ""
    focus_label: str = ""
    result_path: str = ""
    source_shape: str = ""

    @property
    def blocks_enrichment(self) -> bool:
        return self.severity.endswith("Violation")


class EnrichmentValidation(BaseModel):
    ok: bool
    attempts: int
    unknown_iris: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    shacl_conforms: bool = True
    shacl_findings: list[ShaclFinding] = Field(default_factory=list)


class EnrichmentResult(BaseModel):
    enriched: dict[str, Any]
    diff: list[EnrichmentDiffItem]
    validation: EnrichmentValidation
