from datetime import datetime, timezone
import secrets

from fastapi import Request

from copilot.api_keys import hash_api_key, lookup_api_key_by_hash, touch_last_used
from copilot.auth.models import User
from copilot.core.config import get_settings

SERVICE_NAME_HEADER = "X-Registry-Service"
SERVICE_TOKEN_HEADER = "X-Registry-Service-Token"

SERVICE_SCOPES = {
    "wot_runtime": [
        "things:read",
        "wot:read",
        "content:read",
        "content:write",
    ],
}


def _service_token_for(settings, service_name: str) -> str | None:
    if service_name == "wot_runtime":
        return settings.WOT_RUNTIME_REGISTRY_TOKEN
    return None


def _get_service_user(request: Request) -> User | None:
    settings = get_settings()
    service_name = request.headers.get(SERVICE_NAME_HEADER, "").strip()
    service_token = request.headers.get(SERVICE_TOKEN_HEADER, "")
    if not service_name or not service_token:
        return None

    expected_token = _service_token_for(settings, service_name)
    if not expected_token:
        return None
    if not secrets.compare_digest(service_token, expected_token):
        return None

    scopes = list(SERVICE_SCOPES.get(service_name, ()))
    return User(
        user_id=f"service:{service_name}",
        preferred_username=service_name,
        scopes=scopes,
        auth_type="service",
        service_id=service_name,
    )


def get_api_key_user(request: Request) -> User | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    key_hash = hash_api_key(token)
    with request.app.state.connection_pool.connection() as connection:
        row = lookup_api_key_by_hash(connection, key_hash)
        if row is None or not row.is_active:
            return None
        if row.expires_at is not None and row.expires_at < datetime.now(timezone.utc):
            return None

        touch_last_used(connection, row)
        return User(
            user_id=row.user_id,
            scopes=list(row.scopes or []),
            auth_type="api_key",
        )


def get_current_user(request: Request) -> User | None:
    service_user = _get_service_user(request)
    if service_user is not None:
        return service_user

    api_key_user = get_api_key_user(request)
    if api_key_user is not None:
        return api_key_user

    return None
