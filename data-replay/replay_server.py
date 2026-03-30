#!/usr/bin/env python3
"""Replay server that serves historical IoT data with time remapping
and registers generated Thing Descriptions with the wot-registry.

Time remapping:
    The data covers a fixed window (e.g. Jan 1–31). Current real time is
    mapped into that window using modulo arithmetic, so the data loops.
    Returned timestamps are shifted forward to look current.

    Example: data is Jan 1–31 (30 days). Today is Mar 30 20:35.
    → virtual time = Jan 30 20:35 (89 days since Jan 1, mod 30 = 29 days)
    → data point at Jan 30 20:30 is returned with timestamp Mar 30 20:30

Environment variables:
    DB_PATH              - Path to fixtures.db (default: fixtures.db)
    REPLAY_BASE_URL      - Public URL of this server (default: http://localhost:9000)
    WOT_REGISTRY_URL     - wot-registry API base URL (e.g. http://wot-registry:8000)
    WOT_REGISTRY_TOKEN   - Bearer token for wot-registry API
"""

import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from td_generator import generate_td

logger = logging.getLogger("replay_server")

DB_PATH = os.environ.get("DB_PATH", "fixtures.db")
REPLAY_BASE_URL = os.environ.get("REPLAY_BASE_URL", "http://localhost:9000")
WOT_REGISTRY_URL: str | None = os.environ.get("WOT_REGISTRY_URL")
WOT_REGISTRY_TOKEN: str | None = os.environ.get("WOT_REGISTRY_TOKEN")

# Data window bounds (set at startup)
_data_start_ms: int = 0
_data_end_ms: int = 0
_data_duration_ms: int = 0

ONE_DAY_MS = 24 * 60 * 60 * 1000


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _now_ms() -> int:
    return int(time.time() * 1000)


def _real_to_virtual(real_ms: int) -> int:
    """Map a real-world timestamp into the data window using modulo."""
    offset = (real_ms - _data_start_ms) % _data_duration_ms
    return _data_start_ms + offset


def _time_offset() -> int:
    """Current offset to shift data timestamps to real time.

    Add this to a data timestamp to make it look current.
    """
    now = _now_ms()
    virtual_now = _real_to_virtual(now)
    return now - virtual_now


def _db_property(prop: str) -> str:
    """Re-encode a URL-decoded property name to match the DB key."""
    return quote(prop, safe="")


def _fetch_history_rows(
    conn: sqlite3.Connection,
    device_id: str,
    db_prop: str,
    start_ts: int,
    end_ts: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT ts, value FROM readings
        WHERE device_id = ? AND property = ? AND ts >= ? AND ts <= ?
        ORDER BY ts ASC
        """,
        (device_id, db_prop, start_ts, end_ts),
    ).fetchall()


def _iter_history_segments(from_ms: int, to_ms: int):
    """Yield virtual DB slices that cover a real request window."""
    remaining = to_ms - from_ms
    virtual_cursor = _real_to_virtual(from_ms)
    base_offset = from_ms - virtual_cursor
    cycle_offset = 0

    while True:
        segment_end = min(_data_end_ms, virtual_cursor + remaining)
        yield virtual_cursor, segment_end, base_offset + cycle_offset

        consumed = segment_end - virtual_cursor
        if consumed >= remaining:
            return

        remaining -= consumed
        virtual_cursor = _data_start_ms
        cycle_offset += _data_duration_ms


def _load_devices() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT definition FROM devices").fetchall()
    conn.close()
    return [json.loads(row["definition"]) for row in rows]


async def _register_things(devices: list[dict]):
    if not WOT_REGISTRY_URL or not WOT_REGISTRY_TOKEN:
        logger.warning(
            "WOT_REGISTRY_URL or WOT_REGISTRY_TOKEN not set — skipping TD registration"
        )
        return

    registry_api = WOT_REGISTRY_URL.rstrip("/") + "/api/things"
    headers = {
        "Authorization": f"Bearer {WOT_REGISTRY_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        for device in devices:
            td = generate_td(device, REPLAY_BASE_URL)
            title = td["title"]
            try:
                resp = await client.post(registry_api, json=td, headers=headers)
                if resp.status_code in (200, 201):
                    logger.info(f"Registered: {title} ({td['id']})")
                elif resp.status_code == 409:
                    thing_id = td["id"]
                    put_url = f"{registry_api}/{thing_id}"
                    resp = await client.put(put_url, json=td, headers=headers)
                    if resp.status_code in (200, 201):
                        logger.info(f"Updated: {title} ({thing_id})")
                    else:
                        logger.error(
                            f"Failed to update {title}: {resp.status_code} {resp.text}"
                        )
                else:
                    logger.error(
                        f"Failed to register {title}: {resp.status_code} {resp.text}"
                    )
            except Exception as e:
                logger.error(f"Failed to register {title}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _data_start_ms, _data_end_ms, _data_duration_ms

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    conn = get_db()
    row = conn.execute(
        "SELECT MIN(ts) as min_ts, MAX(ts) as max_ts FROM readings"
    ).fetchone()
    conn.close()

    _data_start_ms = row["min_ts"] or 0
    _data_end_ms = row["max_ts"] or 0
    _data_duration_ms = _data_end_ms - _data_start_ms

    if _data_duration_ms <= 0:
        logger.error("No data in database or zero-length window")
    else:
        start = datetime.fromtimestamp(_data_start_ms / 1000, tz=timezone.utc)
        end = datetime.fromtimestamp(_data_end_ms / 1000, tz=timezone.utc)
        days = _data_duration_ms / (24 * 3600 * 1000)
        logger.info(
            f"Data window: {start.isoformat()} to {end.isoformat()} ({days:.1f} days)"
        )

        virtual_now = _real_to_virtual(_now_ms())
        vt = datetime.fromtimestamp(virtual_now / 1000, tz=timezone.utc)
        logger.info(f"Current virtual time: {vt.isoformat()}")

    devices = _load_devices()
    logger.info(f"Loaded {len(devices)} device definitions from DB")
    await _register_things(devices)

    yield


app = FastAPI(title="Data Replay Server", lifespan=lifespan)


@app.get("/health")
async def health():
    virtual_now = _real_to_virtual(_now_ms())
    vt = datetime.fromtimestamp(virtual_now / 1000, tz=timezone.utc)
    offset = _time_offset()
    return {
        "status": "ok",
        "virtual_time": vt.isoformat(),
        "offset_hours": round(offset / 3600000, 1),
    }


@app.get("/api/history/{device_id}/{property}/latest")
async def get_latest(
    device_id: str,
    property: str,
    includeTimestamps: bool = Query(default=True),
):
    virtual_now = _real_to_virtual(_now_ms())
    offset = _time_offset()
    db_prop = _db_property(property)

    conn = get_db()
    row = conn.execute(
        """
        SELECT ts, value FROM readings
        WHERE device_id = ? AND property = ? AND ts <= ?
        ORDER BY ts DESC LIMIT 1
        """,
        (device_id, db_prop, virtual_now),
    ).fetchone()
    conn.close()

    if row is None:
        return JSONResponse(content={}, status_code=200)

    result = json.loads(row["value"])
    if includeTimestamps:
        result["ts"] = row["ts"] + offset
    return JSONResponse(content=result)


@app.get("/api/history/{device_id}/{property}")
async def get_history(
    device_id: str,
    property: str,
    from_: int | None = Query(default=None, alias="from"),
    to: int | None = Query(default=None),
):
    db_prop = _db_property(property)

    # Default: last 24 hours
    if from_ is None and to is None:
        to = _now_ms()
        from_ = to - ONE_DAY_MS
    elif from_ is None:
        from_ = to - ONE_DAY_MS
    elif to is None:
        to = from_ + ONE_DAY_MS

    if to < from_:
        return JSONResponse(
            content={"detail": "'to' must be greater than or equal to 'from'"},
            status_code=400,
        )

    conn = get_db()

    result = []
    for segment_start, segment_end, offset in _iter_history_segments(from_, to):
        rows = _fetch_history_rows(
            conn,
            device_id,
            db_prop,
            segment_start,
            segment_end,
        )
        for row in rows:
            entry = json.loads(row["value"])
            entry["ts"] = row["ts"] + offset
            result.append(entry)

    conn.close()

    return JSONResponse(content=result)
