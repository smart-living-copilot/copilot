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
from copilot.rdf.federation import (
    endpoint_proxy_url,
    proxy_sparql_request,
    resolve_federated_endpoint,
    thing_id_from_proxy_path,
)
from copilot.rdf.models import RdfQueryRequest, RdfQueryResponse, RdfReindexResponse
from copilot.rdf.store import RdfStoreService

logger = logging.getLogger(__name__)


def _settings_from_app(request: Request) -> Any:
    return request.app.state.settings


def _rdf_store(request: Request) -> RdfStoreService:
    return request.app.state.rdf_store


def _load_all_things() -> list[tuple[str, dict[str, Any]]]:
    session_factory = get_session_factory()
    with session_factory() as session:
        things = session.scalars(select(Thing).order_by(Thing.id)).all()
        return [(record.id, record.document) for record in (to_record(thing) for thing in things)]


def _service_rewrites(endpoint_ids: list[str], settings: Any) -> dict[str, str]:
    rewrites: dict[str, str] = {}
    session_factory = get_session_factory()
    with session_factory() as session:
        for endpoint_id in dict.fromkeys(endpoint_ids):
            resolve_federated_endpoint(session, thing_id=endpoint_id, settings=settings)
            rewrites[endpoint_id] = endpoint_proxy_url(
                settings.RDF_FEDERATION_PROXY_BASE_URL,
                endpoint_id,
            )
    return rewrites


def _resolve_proxy_endpoint(thing_id: str, settings: Any):
    session_factory = get_session_factory()
    with session_factory() as session:
        return resolve_federated_endpoint(session, thing_id=thing_id, settings=settings)


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
    settings = _settings_from_app(request)
    try:
        service_rewrites = await asyncio.to_thread(
            _service_rewrites,
            payload.endpoints,
            settings,
        )
        return await _rdf_store(request).query(
            query=payload.query,
            limit=payload.limit,
            use_default_graph_as_union=payload.use_default_graph_as_union,
            service_rewrites=service_rewrites,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/rdf/reindex", response_model=RdfReindexResponse)
async def reindex_rdf(request: Request) -> dict[str, Any]:
    verify_internal_api_key(request)
    things = await asyncio.to_thread(_load_all_things)
    result = await _rdf_store(request).reindex(things)
    return {
        "indexed": result.indexed,
        "failed": result.failed,
        "errors": result.errors,
    }


@app.api_route("/rdf/federate/{encoded_thing_id:path}", methods=["GET", "POST"])
async def federate_sparql(encoded_thing_id: str, request: Request):
    settings = _settings_from_app(request)
    thing_id = thing_id_from_proxy_path(encoded_thing_id)
    try:
        endpoint = await asyncio.to_thread(_resolve_proxy_endpoint, thing_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await proxy_sparql_request(request, endpoint=endpoint, settings=settings)
