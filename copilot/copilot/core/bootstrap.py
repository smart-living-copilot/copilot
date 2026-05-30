import logging

from copilot.api_keys import ensure_init_admin_key
from copilot.core.config import Settings
from copilot.core.database import DatabaseConnection

logger = logging.getLogger(__name__)

INIT_ADMIN_USER_ID = "init-admin"


class BackendBootstrapService:
    def __init__(self, connection: DatabaseConnection):
        self._connection = connection

    def bootstrap(self, settings: Settings) -> None:
        if not settings.INIT_ADMIN_TOKEN:
            return

        created = ensure_init_admin_key(
            self._connection,
            settings.INIT_ADMIN_TOKEN,
            INIT_ADMIN_USER_ID,
        )
        if created:
            logger.info("Created init admin API key")
