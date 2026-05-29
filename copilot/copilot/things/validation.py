from fastapi import HTTPException
from jsonschema import ValidationError

from copilot.things.models import ThingDocument
from copilot.things.store import sanitize_document
from copilot.things.schema import format_validation_error, validate_thing_document


def validate_document(document: ThingDocument) -> ThingDocument:
    sanitized = sanitize_document(document)
    try:
        validate_thing_document(sanitized)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=format_validation_error(exc),
        ) from exc

    return sanitized
