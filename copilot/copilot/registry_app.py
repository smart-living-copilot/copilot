from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from copilot.config import get_settings
from copilot.database import get_session_factory, init_db
from copilot.health import router as health_router
from copilot.lifecycle import shutdown_backend_runtime, start_backend_runtime
import copilot.api_keys.models  # noqa: F401 — register table before init_db()
import copilot.things.credentials.models  # noqa: F401 — register table before init_db()
import copilot.things.events.models  # noqa: F401 — register table before init_db()
import copilot.things.models  # noqa: F401 — register table before init_db()

from copilot.api_keys.router import router as api_keys_router
from copilot.auth.router import router as me_router
from copilot.runtime.router import router as wot_operations_router
from copilot.search.router import router as search_router
from copilot.things.router import router as things_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    init_db()
    session_factory = get_session_factory()
    await start_backend_runtime(
        app,
        settings=settings,
        session_factory=session_factory,
    )

    yield

    await shutdown_backend_runtime(app)


app = FastAPI(
    title="wot_registry registry",
    description="Registry API for the WoT catalog and API-key-authenticated access.",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(me_router)
app.include_router(search_router)
app.include_router(things_router)
app.include_router(api_keys_router)
app.include_router(wot_operations_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
