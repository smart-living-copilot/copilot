from datetime import datetime

from fastapi import HTTPException

from copilot.api_keys.store import create_api_key, list_api_keys, revoke_api_key
from copilot.auth.models import User
from copilot.api_keys.models import ApiKeyRecord
from copilot.core.database import DatabaseConnection


class ApiKeyManagementService:
    def __init__(self, connection: DatabaseConnection):
        self._connection = connection

    def create_for_user(
        self,
        *,
        user: User,
        name: str,
        scopes: list[str],
        expires_at: datetime | None = None,
    ) -> tuple[ApiKeyRecord, str]:
        if user.scopes is not None:
            allowed_scopes = set(user.scopes)
            missing_scopes = set(scopes) - allowed_scopes
            if missing_scopes:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Cannot create API key with scopes you do not have: "
                        + ", ".join(sorted(missing_scopes))
                    ),
                )

        try:
            return create_api_key(
                self._connection,
                user_id=user.user_id,
                name=name,
                scopes=scopes,
                expires_at=expires_at,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def list_for_user(self, user_id: str) -> list[ApiKeyRecord]:
        return list_api_keys(self._connection, user_id)

    def revoke_for_user(self, key_id: str, user_id: str) -> None:
        revoked = revoke_api_key(self._connection, key_id, user_id)
        if not revoked:
            raise HTTPException(status_code=404, detail="API key not found")
