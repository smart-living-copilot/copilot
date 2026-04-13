"""FastAPI app for specialist-agent runtime."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request

from specialist_agent.models import ExecuteRequest, ExecuteResponse, Settings
from specialist_agent.service import SpecialistService

logger = logging.getLogger(__name__)

_settings: Settings | None = None
_service: SpecialistService | None = None


def _verify_internal_api_key(request: Request) -> None:
    if _settings is None or not _settings.internal_api_key:
        return

    expected = f"Bearer {_settings.internal_api_key}"
    if request.headers.get("authorization", "") != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _settings, _service
    _settings = Settings()
    logging.basicConfig(level=_settings.log_level)
    _service = SpecialistService(_settings)
    yield


app = FastAPI(title="Specialist Agent Runtime", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/agents/search")
async def search_agents(request: Request, q: str = Query(min_length=1)):
    _verify_internal_api_key(request)

    if _service is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    try:
        return await _service.list_agents(q)
    except Exception as exc:
        logger.exception("Search failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/agents/execute", response_model=ExecuteResponse)
async def execute_agent(request: Request, payload: ExecuteRequest):
    _verify_internal_api_key(request)

    if _service is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    try:
        return await _service.execute(
            query=payload.query,
            preferred_agent_id=payload.preferred_agent_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Execution failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
