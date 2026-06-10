from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import select

from copilot.catalog.models import Thing
from copilot.catalog.store import to_record
from copilot.core.api_dependencies import verify_internal_api_key
from copilot.core.config import get_settings
from copilot.core.database import get_session_factory, init_db
from copilot.rdf.consumer import RdfConsumerState, RdfStreamConsumer
from copilot.rdf.models import RdfQueryRequest, RdfQueryResponse, RdfReindexResponse
from copilot.rdf.store import RdfStoreService

logger = logging.getLogger(__name__)


def _settings_from_app(request: Request) -> Any:
    return request.app.state.settings


def _rdf_store(request: Request) -> RdfStoreService:
    return request.app.state.rdf_store


def _load_all_things() -> list[tuple[str, dict[str, Any]]]:
    with get_session_factory() as session:
        things = session.scalars(select(Thing).order_by(Thing.id)).all()
        return [(record.id, record.document) for record in (to_record(thing) for thing in things)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    await asyncio.to_thread(init_db)
    rdf_store = RdfStoreService(settings.RDF_STORE_PATH)
    state = RdfConsumerState()
    stop_event = asyncio.Event()
    consumer = RdfStreamConsumer(
        settings=settings,
        state=state,
        rdf_store=rdf_store,
    )
    task = asyncio.create_task(consumer.run_forever(stop_event))

    app.state.settings = settings
    app.state.rdf_store = rdf_store
    app.state.rdf_consumer_state = state
    app.state.rdf_consumer_task = task
    app.state.rdf_consumer_stop_event = stop_event
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await consumer.close()


app = FastAPI(title="Smart Living Copilot RDF Service", lifespan=lifespan)


@app.get("/health")
@app.get("/health/live")
async def health(request: Request) -> dict[str, Any]:
    settings = _settings_from_app(request)
    state = request.app.state.rdf_consumer_state
    return {
        "status": "ok",
        "store_path": settings.RDF_STORE_PATH,
        "consumer_running": bool(state.loop_running),
        "last_entry_id": state.last_entry_id,
        "last_error": state.last_error,
    }


@app.post("/rdf/query", response_model=RdfQueryResponse)
async def query_rdf(request: Request, payload: RdfQueryRequest) -> dict[str, Any]:
    verify_internal_api_key(request)
    try:
        return await _rdf_store(request).query(
            query=payload.query,
            limit=payload.limit,
            use_default_graph_as_union=payload.use_default_graph_as_union,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/rdf/reindex", response_model=RdfReindexResponse)
async def reindex_rdf(request: Request) -> dict[str, int]:
    verify_internal_api_key(request)
    things = await asyncio.to_thread(_load_all_things)
    indexed = await _rdf_store(request).reindex(things)
    return {"indexed": indexed}
