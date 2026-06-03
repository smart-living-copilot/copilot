"""API key domain for service authentication.

This package owns key hashing, generation, listing, lookup, and lifecycle
operations (including bootstrap of the initial admin key and usage tracking)
used by auth middleware and protected routes.
"""

from copilot.core.scopes import API_KEY_SCOPES, VALID_SCOPES
from copilot.api_keys.store import (
    create_api_key,
    ensure_init_admin_key,
    generate_api_key,
    hash_api_key,
    list_api_keys,
    lookup_api_key_by_hash,
    revoke_api_key,
    touch_last_used,
)

__all__ = [
    "API_KEY_SCOPES",
    "VALID_SCOPES",
    "create_api_key",
    "ensure_init_admin_key",
    "generate_api_key",
    "hash_api_key",
    "list_api_keys",
    "lookup_api_key_by_hash",
    "revoke_api_key",
    "touch_last_used",
]
