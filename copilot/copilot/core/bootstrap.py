import logging

from sqlalchemy.orm import Session

from copilot.api_keys import ensure_init_admin_key
from copilot.core.config import Settings

logger = logging.getLogger(__name__)

INIT_ADMIN_USER_ID = "init-admin"


class BackendBootstrapService:
    def __init__(self, session: Session):
        self._session = session

    def bootstrap(self, settings: Settings) -> None:
        if not settings.INIT_ADMIN_TOKEN:
            return

        created = ensure_init_admin_key(
            self._session,
            settings.INIT_ADMIN_TOKEN,
            INIT_ADMIN_USER_ID,
        )
        if created:
            logger.info("Created init admin API key")
