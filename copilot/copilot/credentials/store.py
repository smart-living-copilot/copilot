import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from copilot.credentials.models import CredentialRow

_SENSITIVE_FIELDS = {"password", "token", "apiKey"}


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


def _get_credential_row(
    session: Session,
    *,
    thing_id: str,
    security_name: str,
) -> CredentialRow | None:
    stmt = select(CredentialRow).where(
        CredentialRow.thing_id == thing_id,
        CredentialRow.security_name == security_name,
    )
    return session.execute(stmt).scalar_one_or_none()


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
    session: Session,
    thing_id: str,
    security_name: str,
    scheme: str,
    credentials: dict[str, Any],
) -> CredentialRow:
    """Upsert a credential for a thing's security definition."""
    row = _get_credential_row(
        session,
        thing_id=thing_id,
        security_name=security_name,
    )

    if row is not None:
        row.scheme = scheme
        row.credentials = credentials
        row.updated_at = _utcnow()
    else:
        row = CredentialRow(
            id=str(uuid.uuid4()),
            thing_id=thing_id,
            security_name=security_name,
            scheme=scheme,
            credentials=credentials,
        )
        session.add(row)

    session.commit()
    session.refresh(row)
    return row


def get_credential(
    session: Session, thing_id: str, security_name: str
) -> CredentialRow | None:
    return _get_credential_row(
        session,
        thing_id=thing_id,
        security_name=security_name,
    )


def list_credentials(session: Session, thing_id: str) -> list[dict[str, Any]]:
    """List credentials for a thing with masked sensitive values."""
    stmt = (
        select(CredentialRow)
        .where(CredentialRow.thing_id == thing_id)
        .order_by(CredentialRow.security_name)
    )
    rows = session.execute(stmt).scalars().all()
    return [_serialize_credential_row(row) for row in rows]


def delete_credential(session: Session, thing_id: str, security_name: str) -> bool:
    row = _get_credential_row(
        session,
        thing_id=thing_id,
        security_name=security_name,
    )
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def get_runtime_secrets(session: Session) -> dict[str, Any]:
    """Return credentials keyed by Thing id for runtime consumption."""
    stmt = select(CredentialRow).order_by(
        CredentialRow.thing_id,
        CredentialRow.security_name,
    )
    rows = session.execute(stmt).scalars().all()
    secrets: dict[str, Any] = {}
    for row in rows:
        _append_runtime_secret(
            secrets,
            row=row,
        )
    return secrets
