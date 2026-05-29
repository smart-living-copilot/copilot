from fastapi import Request

from copilot.auth import get_current_user
from copilot.core.config import get_settings


def _request_with_headers(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in headers.items()
        ],
    }
    return Request(scope)


def test_get_current_user_returns_none_without_headers():
    request = _request_with_headers({})

    user = get_current_user(request)

    assert user is None


def test_get_current_user_accepts_configured_service_token(monkeypatch):
    monkeypatch.setenv("WOT_RUNTIME_REGISTRY_TOKEN", "runtime-secret")
    get_settings.cache_clear()

    request = _request_with_headers(
        {
            "X-Registry-Service": "wot_runtime",
            "X-Registry-Service-Token": "runtime-secret",
        }
    )

    user = get_current_user(request)

    assert user is not None
    assert user.user_id == "service:wot_runtime"
    assert user.service_id == "wot_runtime"
    assert user.auth_type == "service"
    assert user.scopes == [
        "things:read",
        "wot:read",
        "content:read",
        "content:write",
    ]


def test_get_current_user_rejects_invalid_service_token(monkeypatch):
    monkeypatch.setenv("WOT_RUNTIME_REGISTRY_TOKEN", "runtime-secret")
    get_settings.cache_clear()

    request = _request_with_headers(
        {
            "X-Registry-Service": "wot_runtime",
            "X-Registry-Service-Token": "wrong-secret",
        }
    )

    user = get_current_user(request)

    assert user is None
