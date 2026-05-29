from copilot.auth.dependencies import require_scopes, require_service, require_user
from copilot.auth.models import User
from copilot.auth.providers import (
    SERVICE_NAME_HEADER,
    SERVICE_SCOPES,
    SERVICE_TOKEN_HEADER,
    get_api_key_user,
    get_current_user,
)

__all__ = [
    "SERVICE_NAME_HEADER",
    "SERVICE_SCOPES",
    "SERVICE_TOKEN_HEADER",
    "User",
    "get_api_key_user",
    "get_current_user",
    "require_scopes",
    "require_service",
    "require_user",
]
