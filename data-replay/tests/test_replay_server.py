import json
import sqlite3
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi.testclient import TestClient

import replay_server


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


class ReplayHistoryTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._original_lifespan_context = replay_server.app.router.lifespan_context
        replay_server.app.router.lifespan_context = _noop_lifespan

    @classmethod
    def tearDownClass(cls) -> None:
        replay_server.app.router.lifespan_context = cls._original_lifespan_context

    def setUp(self) -> None:
        self._original_db_path = replay_server.DB_PATH
        self._original_data_start = replay_server._data_start_ms
        self._original_data_end = replay_server._data_end_ms
        self._original_data_duration = replay_server._data_duration_ms

        self._temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._temp_dir.name) / "fixtures.db"
        self._create_fixture_db(self.db_path)

        replay_server.DB_PATH = str(self.db_path)
        replay_server._data_start_ms = 1000
        replay_server._data_end_ms = 5000
        replay_server._data_duration_ms = 4000

        self.client = TestClient(replay_server.app)

    def tearDown(self) -> None:
        self.client.close()
        replay_server.DB_PATH = self._original_db_path
        replay_server._data_start_ms = self._original_data_start
        replay_server._data_end_ms = self._original_data_end
        replay_server._data_duration_ms = self._original_data_duration
        self._temp_dir.cleanup()

    def test_history_returns_rows_for_a_range_inside_one_cycle(self) -> None:
        response = self.client.get(
            "/api/history/device-a/power",
            params={"from": 1500, "to": 4500},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {"power": 15, "ts": 1500},
                {"power": 25, "ts": 2500},
                {"power": 35, "ts": 3500},
                {"power": 45, "ts": 4500},
            ],
        )

    def test_history_wraps_once_when_range_crosses_the_global_window_end(self) -> None:
        response = self.client.get(
            "/api/history/device-a/power",
            params={"from": 3200, "to": 6200},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {"power": 35, "ts": 3500},
                {"power": 45, "ts": 4500},
                {"power": 15, "ts": 5500},
            ],
        )

    def test_history_repeats_data_for_ranges_larger_than_one_cycle(self) -> None:
        response = self.client.get(
            "/api/history/device-a/power",
            params={"from": 1500, "to": 10500},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {"power": 15, "ts": 1500},
                {"power": 25, "ts": 2500},
                {"power": 35, "ts": 3500},
                {"power": 45, "ts": 4500},
                {"power": 15, "ts": 5500},
                {"power": 25, "ts": 6500},
                {"power": 35, "ts": 7500},
                {"power": 45, "ts": 8500},
                {"power": 15, "ts": 9500},
                {"power": 25, "ts": 10500},
            ],
        )

    @staticmethod
    def _create_fixture_db(db_path: Path) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE readings (
                    device_id TEXT NOT NULL,
                    property TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    value TEXT NOT NULL
                )
                """
            )
            conn.executemany(
                """
                INSERT INTO readings (device_id, property, ts, value)
                VALUES (?, ?, ?, ?)
                """,
                [
                    ("window-bounds", "power", 1000, json.dumps({"power": 0})),
                    ("window-bounds", "power", 5000, json.dumps({"power": 0})),
                    ("device-a", "power", 1500, json.dumps({"power": 15})),
                    ("device-a", "power", 2500, json.dumps({"power": 25})),
                    ("device-a", "power", 3500, json.dumps({"power": 35})),
                    ("device-a", "power", 4500, json.dumps({"power": 45})),
                ],
            )
            conn.commit()


if __name__ == "__main__":
    unittest.main()
