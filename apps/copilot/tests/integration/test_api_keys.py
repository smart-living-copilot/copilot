from __future__ import annotations

from dataclasses import replace

import pytest

from copilot.api_keys.store import (
    create_api_key,
    ensure_init_admin_key,
    hash_api_key,
    list_api_keys,
    lookup_api_key_by_hash,
    revoke_api_key,
    touch_last_used,
)
from copilot.core.config import get_settings
from copilot.core.database import get_session_factory
from copilot.core.lifecycle import bootstrap_persistent_state
from copilot.core.scopes import API_KEY_SCOPES

pytestmark = pytest.mark.integration


def test_api_key_store_round_trips_with_sqlalchemy(jobs_integration_environment) -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        record, raw_key = create_api_key(
            session,
            user_id="user-1",
            name="demo key",
            scopes=["things:read"],
        )

    with session_factory() as session:
        row = lookup_api_key_by_hash(session, hash_api_key(raw_key))
        assert row is not None
        assert row.id == record.id
        assert row.scopes == ["things:read"]
        touch_last_used(session, row)

    with session_factory() as session:
        listed = list_api_keys(session, "user-1")
        assert [item.id for item in listed] == [record.id]
        assert listed[0].last_used_at is not None
        assert revoke_api_key(session, record.id, "user-1") is True

    with session_factory() as session:
        assert list_api_keys(session, "user-1") == []


def test_init_admin_key_is_refreshed_with_sqlalchemy(jobs_integration_environment) -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        assert ensure_init_admin_key(session, "test-init-admin-token", "init-admin") is True

    with session_factory() as session:
        assert ensure_init_admin_key(session, "test-init-admin-token", "new-owner") is False

    with session_factory() as session:
        row = lookup_api_key_by_hash(session, hash_api_key("test-init-admin-token"))
        assert row is not None
        assert row.user_id == "new-owner"
        assert set(row.scopes) == set(API_KEY_SCOPES)
        assert row.is_active is True


def test_backend_bootstrap_creates_init_admin_key(jobs_integration_environment) -> None:
    bootstrap_persistent_state(
        settings=replace(get_settings(), INIT_ADMIN_TOKEN="bootstrap-token")
    )

    session_factory = get_session_factory()
    with session_factory() as session:
        row = lookup_api_key_by_hash(session, hash_api_key("bootstrap-token"))
        assert row is not None
        assert row.user_id == "init-admin"
        assert set(row.scopes) == set(API_KEY_SCOPES)
