"""Thing credential management for runtime integrations.

This package stores and retrieves per-thing security credentials for runtime
tooling and exposes secret metadata for runtime wiring.
"""

from copilot.catalog.credentials.store import (
    delete_credential,
    get_credential,
    get_runtime_secrets,
    list_credentials,
    set_credential,
)

__all__ = [
    "delete_credential",
    "get_credential",
    "get_runtime_secrets",
    "list_credentials",
    "set_credential",
]
