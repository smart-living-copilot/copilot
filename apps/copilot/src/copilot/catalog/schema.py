import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate


SCHEMA_PATH = Path(__file__).with_name("td-schema.json")


@lru_cache()
def load_td_schema() -> dict[str, Any]:
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_thing_document(document: dict[str, Any]) -> None:
    validate(instance=document, schema=load_td_schema())


def format_validation_error(error: ValidationError) -> str:
    path = ".".join(str(part) for part in error.path)
    if path:
        return f"{path}: {error.message}"
    return error.message
