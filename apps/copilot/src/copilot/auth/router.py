from fastapi import APIRouter, Depends

from copilot.auth import User, require_user


router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
def get_me(user: User = Depends(require_user)) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "preferred_username": user.preferred_username,
        "groups": user.groups,
        "scopes": user.scopes or [],
    }
