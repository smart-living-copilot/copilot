"""Thing catalog domain.

The catalog package manages normalized WoT thing documents, validation, storage,
serialization, and event generation for downstream indexing and runtime workers.
"""

from copilot.catalog.events import build_change_event, build_remove_event
from copilot.catalog.presentation import serialize_thing
from copilot.catalog.store import (
    create_thing,
    delete_thing,
    get_thing,
    hash_document,
    list_things,
    put_thing,
    sanitize_document,
    serialize_document,
    summarize_document,
    to_record,
)
from copilot.catalog.validation import validate_document

__all__ = [
    "build_change_event",
    "build_remove_event",
    "create_thing",
    "delete_thing",
    "get_thing",
    "hash_document",
    "list_things",
    "put_thing",
    "sanitize_document",
    "serialize_document",
    "serialize_thing",
    "summarize_document",
    "to_record",
    "validate_document",
]
