"""Tool for storing credentials for a Thing's security definition.

The discovery branch uses this to automatically store bearer tokens (or other
credentials) for auto-discovered Things so the runtime can authenticate when
interacting with them.
"""

import asyncio
from typing import Any

from langchain_core.tools import tool

from wotbot.catalog.credentials.service import CredentialService
from wotbot.catalog.ids import decode_thing_id
from wotbot.catalog.store import get_thing as _fetch_thing_record
from wotbot.core.database import get_session_factory


async def _get_thing_record(thing_id: str):
    """Fetch a ThingRecord from the catalog to check its source."""

    def _fetch():
        session_factory = get_session_factory()
        with session_factory() as session:
            return _fetch_thing_record(session, thing_id)

    return await asyncio.to_thread(_fetch)


@tool
async def set_thing_credential(
    thing_id: str,
    security_name: str,
    scheme: str,
    credentials: dict[str, Any],
) -> dict[str, str]:
    """Store authentication credentials for a Thing's security definition.

    IMPORTANT: This tool can ONLY be used on auto-discovered Thing Descriptions
    (source="auto-discovered"). Manually created Things require the user to
    set credentials directly. The runtime automatically injects stored
    credentials into HTTP requests to the Thing — you do NOT need to pass
    tokens in action inputs.

    Common credential formats:
    - Bearer token: scheme="bearer", credentials={"token": "<value>"}
    - API key:      scheme="apikey",  credentials={"apikey": "<value>"}
    - Basic auth:   scheme="basic",   credentials={"username": "...", "password": "..."}
    - No auth:      scheme="nosec",   credentials={}

    Use things_get first to discover the Thing's security definitions and
    determine the correct security_name and scheme.
    """
    decoded_id = decode_thing_id(thing_id)

    # Verify the thing exists and is auto-discovered
    thing_record = await _get_thing_record(decoded_id)
    if thing_record is None:
        return {"status": "error", "message": f"Thing '{thing_id}' not found in catalog"}
    if thing_record.source != "auto-discovered":
        return {
            "status": "error",
            "message": (
                f"Thing '{thing_id}' has source='{thing_record.source}'. "
                "Credentials can only be set on auto-discovered Things "
                "(source='auto-discovered'). Manually created Things require "
                "the user to store credentials via the credentials API directly."
            ),
        }

    errors = _validate_credential_inputs(thing_id, security_name, scheme, credentials)
    if errors:
        return {"status": "error", "message": errors}

    def _store() -> None:
        session_factory = get_session_factory()
        with session_factory() as session:
            CredentialService(session).upsert(
                thing_id=decoded_id,
                security_name=security_name,
                scheme=scheme,
                credentials=credentials,
            )

    try:
        await asyncio.to_thread(_store)
        return {
            "status": "ok",
            "message": (
                f"Credential '{security_name}' ({scheme}) stored for "
                f"'{thing_id}'. The runtime will now inject it automatically."
            ),
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to store credential: {exc}",
        }


def _validate_credential_inputs(
    thing_id: str,
    security_name: str,
    scheme: str,
    credentials: dict[str, Any],
) -> str | None:
    if not thing_id or not thing_id.strip():
        return "thing_id is required"
    if not security_name or not security_name.strip():
        return "security_name is required"
    if not scheme or not scheme.strip():
        return "scheme is required"

    scheme = scheme.lower().strip()
    if scheme not in ("nosec", "bearer", "apikey", "basic", "digest", "oauth2"):
        return f"Unknown scheme '{scheme}'. Supported: nosec, bearer, apikey, basic, digest, oauth2"

    if scheme == "bearer" and "token" not in credentials:
        return "bearer scheme requires credentials with a 'token' field"
    if scheme == "apikey" and "apikey" not in credentials:
        return "apikey scheme requires credentials with an 'apikey' field"
    if scheme == "basic":
        if "username" not in credentials or "password" not in credentials:
            return "basic scheme requires credentials with 'username' and 'password' fields"

    return None