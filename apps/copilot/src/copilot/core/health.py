from fastapi import APIRouter


router = APIRouter(tags=["health"])


@router.get("/")
def root() -> dict[str, object]:
    return {
        "name": "wot_registry_registry",
        "health": "/health",
        "me": "/api/me",
        "things": "/api/things",
        "thing_search": "/api/things/search",
    }


@router.get("/health")
@router.get("/health/live")
@router.get("/api/health")
@router.get("/api/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
@router.get("/api/health/ready")
def health_ready() -> dict[str, str]:
    return {"status": "ok"}
