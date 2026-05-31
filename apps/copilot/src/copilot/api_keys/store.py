import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from copilot.api_keys.models import ApiKeyRecord, ApiKeyRow
from copilot.core.database import DatabaseConnection

VALID_SCOPES = frozenset(
    [
        "things:read",
        "things:write",
        "things:delete",
        "wot:read",
        "wot:write",
        "content:read",
        "content:write",
        "search:read",
        "credentials:read",
        "credentials:write",
        "keys:manage",
    ]
)

_API_KEY_COLUMNS = """
    id, key_prefix, key_hash, name, scopes, user_id, created_at, updated_at,
    expires_at, last_used_at, is_active
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_scopes(scopes: list[str]) -> None:
    invalid = set(scopes) - VALID_SCOPES
    if invalid:
        raise ValueError(f"Invalid scopes: {', '.join(sorted(invalid))}")


def generate_api_key() -> str:
    return "slc_" + secrets.token_urlsafe(32)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _row_from_mapping(row: dict[str, Any]) -> ApiKeyRow:
    return ApiKeyRow(
        id=str(row["id"]),
        key_prefix=str(row["key_prefix"]),
        key_hash=str(row["key_hash"]),
        name=str(row["name"]),
        scopes=list(row["scopes"] or []),
        user_id=str(row["user_id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
        last_used_at=row["last_used_at"],
        is_active=bool(row["is_active"]),
    )


def _to_record(row: ApiKeyRow) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=row.id,
        key_prefix=row.key_prefix,
        name=row.name,
        scopes=list(row.scopes or []),
        user_id=row.user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        is_active=row.is_active,
    )


def create_api_key(
    connection: DatabaseConnection,
    user_id: str,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> tuple[ApiKeyRecord, str]:
    _validate_scopes(scopes)

    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    row = connection.execute(
        f"""
        INSERT INTO api_keys (
            id, key_prefix, key_hash, name, scopes, user_id, expires_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING {_API_KEY_COLUMNS}
        """,
        (
            str(uuid.uuid4()),
            raw_key[:12],
            key_hash,
            name,
            Jsonb(list(scopes)),
            user_id,
            expires_at,
            _utcnow(),
        ),
    ).fetchone()
    connection.commit()
    if row is None:
        raise RuntimeError("API key row was not returned")
    return _to_record(_row_from_mapping(row)), raw_key


def list_api_keys(connection: DatabaseConnection, user_id: str) -> list[ApiKeyRecord]:
    rows = connection.execute(
        f"""
        SELECT {_API_KEY_COLUMNS}
        FROM api_keys
        WHERE user_id = %s AND is_active = true
        ORDER BY created_at DESC
        """,
        (user_id,),
    ).fetchall()
    return [_to_record(_row_from_mapping(row)) for row in rows]


def revoke_api_key(connection: DatabaseConnection, key_id: str, user_id: str) -> bool:
    row = connection.execute(
        """
        UPDATE api_keys
        SET is_active = false, updated_at = %s
        WHERE id = %s AND user_id = %s AND is_active = true
        RETURNING id
        """,
        (_utcnow(), key_id, user_id),
    ).fetchone()
    connection.commit()
    return row is not None


def lookup_api_key_by_hash(
    connection: DatabaseConnection,
    key_hash: str,
) -> ApiKeyRow | None:
    row = connection.execute(
        f"SELECT {_API_KEY_COLUMNS} FROM api_keys WHERE key_hash = %s",
        (key_hash,),
    ).fetchone()
    return _row_from_mapping(row) if row is not None else None


def touch_last_used(connection: DatabaseConnection, row: ApiKeyRow) -> None:
    connection.execute(
        "UPDATE api_keys SET last_used_at = %s WHERE id = %s",
        (_utcnow(), row.id),
    )
    connection.commit()


def ensure_init_admin_key(
    connection: DatabaseConnection,
    raw_token: str,
    user_id: str,
) -> bool:
    """Create an all-scopes API key for *raw_token* if it doesn't already exist.

    Returns True if a new row was inserted, False if it was already present.
    """
    key_hash = hash_api_key(raw_token)
    row = connection.execute(
        f"""
        INSERT INTO api_keys (
            id, key_prefix, key_hash, name, scopes, user_id, expires_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, NULL, %s)
        ON CONFLICT (key_hash) DO NOTHING
        RETURNING {_API_KEY_COLUMNS}
        """,
        (
            str(uuid.uuid4()),
            raw_token[:12],
            key_hash,
            "Init Admin Token",
            Jsonb(sorted(VALID_SCOPES)),
            user_id,
            _utcnow(),
        ),
    ).fetchone()
    connection.commit()
    return row is not None
