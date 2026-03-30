#!/usr/bin/env python3
"""Download historical IoT data and build fixtures.db.

Reads sources.yaml, downloads data from the configured endpoints into a temp
directory, then imports everything into a SQLite database (fixtures.db).

Usage:
    python build_fixtures.py                        # defaults: sources.yaml -> fixtures.db
    python build_fixtures.py -s my_sources.yaml -o my_fixtures.db
    python build_fixtures.py --force-overwrite      # overwrite existing fixtures.db
"""

import argparse
import json
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml


def parse_iso_to_ms(iso_str: str) -> int:
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


# --- Download ---


def download_property(
    base_url: str, device_id: str, prop: str, from_ms: int, to_ms: int
) -> list:
    url = f"{base_url}/api/history/{device_id}/{prop}"
    headers = {"Accept": "application/json"}
    resp = requests.get(
        url, params={"from": from_ms, "to": to_ms}, headers=headers, timeout=120
    )
    resp.raise_for_status()
    return resp.json()


def download_all(config: dict, tmp_dir: Path) -> dict[str, dict]:
    """Download all device properties, returns manifest mapping filename -> metadata."""
    base_url = config["base_url"].rstrip("/")
    from_ms = parse_iso_to_ms(config["from"])
    to_ms = parse_iso_to_ms(config["to"])

    devices = config["devices"]
    total = sum(len(d["properties"]) for d in devices)
    done = 0
    manifest = {}

    for device in devices:
        device_id = device["id"]
        title = device.get("title", device_id)

        for prop in device["properties"]:
            done += 1
            safe_prop = prop.replace("%20", "_").replace("/", "_")
            filename = f"{device_id}_{safe_prop}.json"
            out_file = tmp_dir / filename

            print(
                f"[{done}/{total}] {title} / {prop} ... ",
                end="",
                flush=True,
            )

            try:
                data = download_property(base_url, device_id, prop, from_ms, to_ms)
                with open(out_file, "w") as f:
                    json.dump(data, f)
                manifest[filename] = {"device_id": device_id, "property": prop}
                print(f"OK ({len(data)} records)")
            except Exception as e:
                print(f"FAILED: {e}")

            time.sleep(0.5)

    return manifest


# --- Import ---


def create_schema(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            device_id TEXT NOT NULL,
            property  TEXT NOT NULL,
            ts        INTEGER NOT NULL,
            value     TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id   TEXT PRIMARY KEY,
            definition  TEXT NOT NULL
        )
    """)


def import_readings(
    conn: sqlite3.Connection, filepath: Path, device_id: str, prop: str
) -> int:
    with open(filepath) as f:
        records = json.load(f)

    if not isinstance(records, list):
        return 0

    rows = []
    for record in records:
        ts = record.get("ts")
        if ts is None:
            continue
        value_obj = {k: v for k, v in record.items() if k != "ts"}
        rows.append((device_id, prop, int(ts), json.dumps(value_obj)))

    conn.executemany(
        "INSERT INTO readings (device_id, property, ts, value) VALUES (?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def import_devices(conn: sqlite3.Connection, config: dict) -> int:
    devices = config.get("devices", [])
    for device in devices:
        conn.execute(
            "INSERT INTO devices (device_id, definition) VALUES (?, ?)",
            (device["id"], json.dumps(device)),
        )
    return len(devices)


def build_db(config: dict, manifest: dict[str, dict], tmp_dir: Path, db_path: Path):
    conn = sqlite3.connect(db_path)
    create_schema(conn)

    device_count = import_devices(conn, config)
    print(f"\nImported {device_count} device definitions")

    total_rows = 0
    for filename, meta in manifest.items():
        filepath = tmp_dir / filename
        if not filepath.exists():
            print(f"  Skipping {filename} (file not found)")
            continue

        device_id = meta["device_id"]
        prop = meta["property"]
        count = import_readings(conn, filepath, device_id, prop)
        total_rows += count
        print(f"  {filename}: {count} records")

    print("\nCreating indexes ...")
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_lookup
        ON readings (device_id, property, ts)
    """)

    conn.commit()
    conn.close()

    print(f"Done. {total_rows} readings + {device_count} devices -> {db_path}")


# --- Main ---


def main():
    parser = argparse.ArgumentParser(
        description="Download IoT history data and build fixtures.db"
    )
    parser.add_argument(
        "-s", "--sources", default="sources.yaml", help="Path to sources.yaml"
    )
    parser.add_argument(
        "-o", "--output", default="fixtures.db", help="Output SQLite database"
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Overwrite existing fixtures.db",
    )
    args = parser.parse_args()

    sources_path = Path(args.sources)
    if not sources_path.exists():
        print(f"Error: {sources_path} not found", file=sys.stderr)
        sys.exit(1)

    db_path = Path(args.output)
    if db_path.exists() and not args.force_overwrite:
        print(
            f"Error: {db_path} already exists. Use --force-overwrite to replace it.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(sources_path) as f:
        config = yaml.safe_load(f)

    with tempfile.TemporaryDirectory(prefix="data-replay-") as tmp:
        tmp_dir = Path(tmp)

        print(f"Downloading to {tmp_dir} ...\n")
        manifest = download_all(config, tmp_dir)

        if not manifest:
            print("Error: no data downloaded", file=sys.stderr)
            sys.exit(1)

        if db_path.exists():
            db_path.unlink()

        build_db(config, manifest, tmp_dir, db_path)


if __name__ == "__main__":
    main()
