from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class OntologyConfig(BaseModel):
    prefix: str
    namespace: str
    description: str = ""
    terms: str
    use_for: list[str] = Field(default_factory=list)


class EnrichmentConfig(BaseModel):
    ontologies: list[OntologyConfig]
    system_prompt_extra: str = ""
    # Path to an external SHACL shapes Turtle file. Empty -> packaged defaults.
    shapes: str = ""


@lru_cache(maxsize=8)
def load_enrichment_config(path: str = "") -> EnrichmentConfig:
    """Load the enrichment config, optionally overlaying an external override.

    With no ``path`` the packaged ``default.json`` is used verbatim. When ``path``
    is set, that file is treated as an *overlay* onto the packaged default: keys
    it provides win, keys it omits are inherited. This lets a deployment (e.g. a
    demo) override just ``system_prompt_extra`` while keeping the packaged
    ontology stack, whose ``terms``/``shapes`` keep resolving as packaged
    resources. Keys the override *does* provide are resolved relative to the
    override file (``terms``/``shapes`` become absolute), so they are read from
    disk rather than the package.
    """
    default_payload = _load_packaged_json("default.json")
    if not path:
        return EnrichmentConfig.model_validate(default_payload)

    config_path = Path(path)
    override = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(override, dict):
        raise ValueError(f"Enrichment config {path!r} must be a JSON object")

    payload: dict[str, Any] = dict(default_payload)

    if "system_prompt_extra" in override:
        payload["system_prompt_extra"] = override["system_prompt_extra"]

    if "ontologies" in override:
        ontologies = override["ontologies"]
        for ontology in ontologies:
            terms_path = ontology.get("terms") if isinstance(ontology, dict) else None
            if isinstance(terms_path, str) and not Path(terms_path).is_absolute():
                ontology["terms"] = str((config_path.parent / terms_path).resolve())
        payload["ontologies"] = ontologies

    if "shapes" in override:
        shapes_path = override["shapes"]
        if isinstance(shapes_path, str) and shapes_path and not Path(shapes_path).is_absolute():
            shapes_path = str((config_path.parent / shapes_path).resolve())
        payload["shapes"] = shapes_path

    return EnrichmentConfig.model_validate(payload)


def load_term_payload(terms_path: str, *, config_path: str = "") -> list[dict[str, Any]]:
    if Path(terms_path).is_absolute():
        payload = json.loads(Path(terms_path).read_text(encoding="utf-8"))
    elif config_path:
        resolved = Path(config_path).parent / terms_path
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    else:
        payload = _load_packaged_json(terms_path)
    if not isinstance(payload, list):
        raise ValueError(f"Term source {terms_path!r} must be a JSON list")
    return payload


def _load_packaged_json(relative_path: str) -> Any:
    root = resources.files("wotbot.catalog.enrichment.data")
    return json.loads((root / relative_path).read_text(encoding="utf-8"))
