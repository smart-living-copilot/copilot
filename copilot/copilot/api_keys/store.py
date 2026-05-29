import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from copilot.api_keys.models import ApiKeyRecord, ApiKeyRow

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


def _build_api_key_row(
    *,
    raw_key: str,
    key_hash: str,
    name: str,
    scopes: list[str],
    user_id: str,
    expires_at: datetime | None,
) -> ApiKeyRow:
    return ApiKeyRow(
        id=str(uuid.uuid4()),
        key_prefix=raw_key[:12],
        key_hash=key_hash,
        name=name,
        scopes=list(scopes),
        user_id=user_id,
        expires_at=expires_at,
        updated_at=_utcnow(),
    )


def create_api_key(
    session: Session,
    user_id: str,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> tuple[ApiKeyRecord, str]:
    _validate_scopes(scopes)

    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    row = _build_api_key_row(
        raw_key=raw_key,
        key_hash=key_hash,
        name=name,
        scopes=scopes,
        user_id=user_id,
        expires_at=expires_at,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_record(row), raw_key


def list_api_keys(session: Session, user_id: str) -> list[ApiKeyRecord]:
    stmt = (
        select(ApiKeyRow)
        .where(ApiKeyRow.user_id == user_id, ApiKeyRow.is_active == True)  # noqa: E712
        .order_by(ApiKeyRow.created_at.desc())
    )
    rows = session.execute(stmt).scalars().all()
    return [_to_record(row) for row in rows]


def revoke_api_key(session: Session, key_id: str, user_id: str) -> bool:
    row = session.get(ApiKeyRow, key_id)
    if row is None or row.user_id != user_id or not row.is_active:
        return False
    row.is_active = False
    row.updated_at = _utcnow()
    session.commit()
    return True


def lookup_api_key_by_hash(session: Session, key_hash: str) -> ApiKeyRow | None:
    stmt = select(ApiKeyRow).where(ApiKeyRow.key_hash == key_hash)
    return session.execute(stmt).scalar_one_or_none()


def touch_last_used(session: Session, row: ApiKeyRow) -> None:
    row.last_used_at = _utcnow()
    session.commit()


def ensure_init_admin_key(session: Session, raw_token: str, user_id: str) -> bool:
    """Create an all-scopes API key for *raw_token* if it doesn't already exist.

    Returns True if a new row was inserted, False if it was already present.
    """
    key_hash = hash_api_key(raw_token)
    existing = lookup_api_key_by_hash(session, key_hash)
    if existing is not None:
        return False

    row = _build_api_key_row(
        raw_key=raw_token,
        key_hash=key_hash,
        name="Init Admin Token",
        scopes=sorted(VALID_SCOPES),
        user_id=user_id,
        expires_at=None,
    )
    session.add(row)
    session.commit()
    return True
