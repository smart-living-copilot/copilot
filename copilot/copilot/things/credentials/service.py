from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from copilot.things.credentials.store import (
    delete_credential,
    get_runtime_secrets,
    list_credentials,
    set_credential,
)


class CredentialService:
    def __init__(self, session: Session):
        self._session = session

    def upsert(
        self,
        *,
        thing_id: str,
        security_name: str,
        scheme: str,
        credentials: dict[str, Any],
    ) -> None:
        set_credential(
            self._session,
            thing_id=thing_id,
            security_name=security_name,
            scheme=scheme,
            credentials=credentials,
        )

    def list_for_thing(self, thing_id: str) -> list[dict[str, Any]]:
        return list_credentials(self._session, thing_id)

    def delete(self, *, thing_id: str, security_name: str) -> None:
        deleted = delete_credential(self._session, thing_id, security_name)
        if not deleted:
            raise HTTPException(status_code=404, detail="Credential not found")

    def get_runtime_secrets(self) -> dict[str, Any]:
        return get_runtime_secrets(self._session)
