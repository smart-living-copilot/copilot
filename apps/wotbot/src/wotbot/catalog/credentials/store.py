import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from wotbot.catalog.credentials.models import CredentialRecord, ThingCredential
from wotbot.core.time import utc_now


def _to_record(credential: ThingCredential) -> CredentialRecord:
    return CredentialRecord(
        id=credential.id,
        thing_id=credential.thing_id,
        security_name=credential.security_name,
        scheme=credential.scheme,
        credentials=dict(credential.credentials or {}),
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


def _get_credential(
    session: Session,
    *,
    thing_id: str,
    security_name: str,
) -> ThingCredential | None:
    return session.scalar(
        select(ThingCredential).where(
            ThingCredential.thing_id == thing_id,
            ThingCredential.security_name == security_name,
        )
    )


def _serialize_credential_record(row: CredentialRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "thing_id": row.thing_id,
        "security_name": row.security_name,
        "scheme": row.scheme,
        "has_credentials": bool(row.credentials),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _append_runtime_secret(
    secrets: dict[str, Any],
    *,
    row: CredentialRecord,
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
) -> CredentialRecord:
    """Upsert a credential for a thing's security definition."""
    now = utc_now()
    stmt = insert(ThingCredential).values(
        id=str(uuid.uuid4()),
        thing_id=thing_id,
        security_name=security_name,
        scheme=scheme,
        credentials=credentials,
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_thing_security",
        set_={
            "scheme": stmt.excluded.scheme,
            "credentials": stmt.excluded.credentials,
            "updated_at": stmt.excluded.updated_at,
        },
    ).returning(ThingCredential)

    credential = session.scalars(
        stmt,
        execution_options={"populate_existing": True},
    ).one()
    return _to_record(credential)


def get_credential(
    session: Session,
    thing_id: str,
    security_name: str,
) -> CredentialRecord | None:
    credential = _get_credential(
        session,
        thing_id=thing_id,
        security_name=security_name,
    )
    return _to_record(credential) if credential is not None else None


def list_credentials(session: Session, thing_id: str) -> list[dict[str, Any]]:
    """List credential metadata for a thing without exposing stored secret values."""
    credentials = session.scalars(
        select(ThingCredential)
        .where(ThingCredential.thing_id == thing_id)
        .order_by(ThingCredential.security_name)
    ).all()
    return [_serialize_credential_record(_to_record(row)) for row in credentials]


def delete_credential(
    session: Session,
    thing_id: str,
    security_name: str,
) -> bool:
    credential = _get_credential(
        session,
        thing_id=thing_id,
        security_name=security_name,
    )
    if credential is None:
        return False

    session.delete(credential)
    session.flush()
    return True


def get_runtime_secrets(session: Session) -> dict[str, Any]:
    """Return credentials keyed by Thing id for runtime consumption."""
    credentials = session.scalars(
        select(ThingCredential).order_by(
            ThingCredential.thing_id,
            ThingCredential.security_name,
        )
    ).all()
    secrets: dict[str, Any] = {}
    for credential in credentials:
        _append_runtime_secret(
            secrets,
            row=_to_record(credential),
        )
    return secrets
