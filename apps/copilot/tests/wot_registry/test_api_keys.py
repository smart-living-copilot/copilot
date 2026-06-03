from fastapi.testclient import TestClient

from copilot.api.main import app


def _create_key(
    client: TestClient,
    headers: dict[str, str],
    *,
    name: str,
    scopes: list[str],
) -> dict[str, object]:
    response = client.post(
        "/api/keys",
        headers={
            **headers,
            "Content-Type": "application/json",
        },
        json={
            "name": name,
            "scopes": scopes,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_bearer_key_requires_keys_manage_scope_for_key_management(
    authenticated_headers,
):
    with TestClient(app) as client:
        created = _create_key(
            client,
            authenticated_headers,
            name="read-only",
            scopes=["things:read"],
        )
        bearer_headers = {"Authorization": f"Bearer {created['raw_key']}"}

        list_response = client.get("/api/keys", headers=bearer_headers)
        assert list_response.status_code == 403
        assert "keys:manage" in list_response.json()["detail"]

        create_response = client.post(
            "/api/keys",
            headers={
                **bearer_headers,
                "Content-Type": "application/json",
            },
            json={
                "name": "child",
                "scopes": ["things:read"],
            },
        )
        assert create_response.status_code == 403
        assert "keys:manage" in create_response.json()["detail"]


def test_key_scope_catalog_lists_external_registry_scopes(authenticated_headers):
    with TestClient(app) as client:
        response = client.get("/api/keys/scopes", headers=authenticated_headers)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            "things:read",
            "things:write",
            "things:delete",
            "search:read",
            "credentials:read",
            "credentials:write",
            "keys:manage",
        ]
    }


def test_api_key_cannot_create_broader_scopes_than_it_has(authenticated_headers):
    with TestClient(app) as client:
        manager = _create_key(
            client,
            authenticated_headers,
            name="manager",
            scopes=["keys:manage", "things:read"],
        )
        bearer_headers = {"Authorization": f"Bearer {manager['raw_key']}"}

        allowed_response = client.post(
            "/api/keys",
            headers={
                **bearer_headers,
                "Content-Type": "application/json",
            },
            json={
                "name": "child-ok",
                "scopes": ["things:read"],
            },
        )
        assert allowed_response.status_code == 201, allowed_response.text

        denied_response = client.post(
            "/api/keys",
            headers={
                **bearer_headers,
                "Content-Type": "application/json",
            },
            json={
                "name": "child-too-broad",
                "scopes": ["keys:manage", "things:write"],
            },
        )
        assert denied_response.status_code == 403
        assert "things:write" in denied_response.json()["detail"]


def test_mcp_scope_is_rejected(authenticated_headers):
    with TestClient(app) as client:
        response = client.post(
            "/api/keys",
            headers={
                **authenticated_headers,
                "Content-Type": "application/json",
            },
            json={
                "name": "old-mcp-client",
                "scopes": ["mcp"],
            },
        )

        assert response.status_code == 422
        assert "mcp" in response.json()["detail"]


def test_removed_runtime_and_content_scopes_are_rejected(authenticated_headers):
    with TestClient(app) as client:
        response = client.post(
            "/api/keys",
            headers={
                **authenticated_headers,
                "Content-Type": "application/json",
            },
            json={
                "name": "old-runtime-client",
                "scopes": ["wot:read", "content:read"],
            },
        )

    assert response.status_code == 422
    assert "content:read" in response.json()["detail"]
    assert "wot:read" in response.json()["detail"]
