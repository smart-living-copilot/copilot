import uuid
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from copilot.core.database import DatabaseConnection
from copilot.things.credentials.models import CredentialRow

_SENSITIVE_FIELDS = {"password", "token", "apiKey"}
_CREDENTIAL_COLUMNS = """
    id, thing_id, security_name, scheme, credentials, created_at, updated_at
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mask_value(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def _mask_credentials(creds: dict[str, Any]) -> dict[str, Any]:
    masked = {}
    for key, value in creds.items():
        if key in _SENSITIVE_FIELDS and isinstance(value, str):
            masked[key] = _mask_value(value)
        else:
            masked[key] = value
    return masked


def _row_from_mapping(row: dict[str, Any]) -> CredentialRow:
    return CredentialRow(
        id=str(row["id"]),
        thing_id=str(row["thing_id"]),
        security_name=str(row["security_name"]),
        scheme=str(row["scheme"]),
        credentials=dict(row["credentials"] or {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _get_credential_row(
    connection: DatabaseConnection,
    *,
    thing_id: str,
    security_name: str,
) -> CredentialRow | None:
    row = connection.execute(
        f"""
        SELECT {_CREDENTIAL_COLUMNS}
        FROM thing_credentials
        WHERE thing_id = %s AND security_name = %s
        """,
        (thing_id, security_name),
    ).fetchone()
    return _row_from_mapping(row) if row is not None else None


def _serialize_credential_row(row: CredentialRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "thing_id": row.thing_id,
        "security_name": row.security_name,
        "scheme": row.scheme,
        "credentials": _mask_credentials(row.credentials),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _append_runtime_secret(
    secrets: dict[str, Any],
    *,
    row: CredentialRow,
) -> None:
    current = secrets.get(row.thing_id)
    if current is None:
        current = {"entries": []}
        secrets[row.thing_id] = current

    current["entries"].append(
        {
            "security_name": row.security_name,
            "scheme": row.scheme,
            "credentials": row.credentials,
        }
    )


def set_credential(
    connection: DatabaseConnection,
    thing_id: str,
    security_name: str,
    scheme: str,
    credentials: dict[str, Any],
) -> CredentialRow:
    """Upsert a credential for a thing's security definition."""
    row = connection.execute(
        f"""
        INSERT INTO thing_credentials (
            id, thing_id, security_name, scheme, credentials, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (thing_id, security_name) DO UPDATE
        SET scheme = EXCLUDED.scheme,
            credentials = EXCLUDED.credentials,
            updated_at = EXCLUDED.updated_at
        RETURNING {_CREDENTIAL_COLUMNS}
        """,
        (
            str(uuid.uuid4()),
            thing_id,
            security_name,
            scheme,
            Jsonb(credentials),
            _utcnow(),
        ),
    ).fetchone()
    connection.commit()
    if row is None:
        raise RuntimeError("Credential row was not returned")
    return _row_from_mapping(row)


def get_credential(
    connection: DatabaseConnection, thing_id: str, security_name: str
) -> CredentialRow | None:
    return _get_credential_row(
        connection,
        thing_id=thing_id,
        security_name=security_name,
    )


def list_credentials(connection: DatabaseConnection, thing_id: str) -> list[dict[str, Any]]:
    """List credentials for a thing with masked sensitive values."""
    rows = connection.execute(
        f"""
        SELECT {_CREDENTIAL_COLUMNS}
        FROM thing_credentials
        WHERE thing_id = %s
        ORDER BY security_name
        """,
        (thing_id,),
    ).fetchall()
    return [_serialize_credential_row(_row_from_mapping(row)) for row in rows]


def delete_credential(
    connection: DatabaseConnection,
    thing_id: str,
    security_name: str,
) -> bool:
    row = connection.execute(
        """
        DELETE FROM thing_credentials
        WHERE thing_id = %s AND security_name = %s
        RETURNING id
        """,
        (thing_id, security_name),
    ).fetchone()
    connection.commit()
    return row is not None


def get_runtime_secrets(connection: DatabaseConnection) -> dict[str, Any]:
    """Return credentials keyed by Thing id for runtime consumption."""
    rows = connection.execute(
        f"""
        SELECT {_CREDENTIAL_COLUMNS}
        FROM thing_credentials
        ORDER BY thing_id, security_name
        """
    ).fetchall()
    secrets: dict[str, Any] = {}
    for row in rows:
        _append_runtime_secret(
            secrets,
            row=_row_from_mapping(row),
        )
    return secrets
