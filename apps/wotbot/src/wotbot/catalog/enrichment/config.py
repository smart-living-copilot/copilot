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
    if path:
        config_path = Path(path)
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        for ontology in payload.get("ontologies", []):
            terms_path = ontology.get("terms")
            if isinstance(terms_path, str) and not Path(terms_path).is_absolute():
                ontology["terms"] = str((config_path.parent / terms_path).resolve())
        shapes_path = payload.get("shapes")
        if isinstance(shapes_path, str) and shapes_path and not Path(shapes_path).is_absolute():
            payload["shapes"] = str((config_path.parent / shapes_path).resolve())
    else:
        payload = _load_packaged_json("default.json")
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
