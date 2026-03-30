import sqlite3
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi.testclient import TestClient

import copilot.server as server
from copilot.models import Settings


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


class ServerRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._original_lifespan_context = server.app.router.lifespan_context
        server.app.router.lifespan_context = _noop_lifespan

    @classmethod
    def tearDownClass(cls) -> None:
        server.app.router.lifespan_context = cls._original_lifespan_context

    def setUp(self) -> None:
        self._original_settings = server._settings
        self.client = TestClient(server.app)

    def tearDown(self) -> None:
        self.client.close()
        server._settings = self._original_settings

    def test_ag_ui_health_route_reports_agent_name(self) -> None:
        response = self.client.get("/ag-ui/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "agent": {
                    "name": "copilot",
                },
            },
        )

    def test_ag_ui_endpoint_validates_required_run_agent_input_fields(self) -> None:
        response = self.client.post("/ag-ui", json={})

        self.assertEqual(response.status_code, 422)
        missing_fields = {error["loc"][-1] for error in response.json()["detail"]}
        self.assertEqual(
            missing_fields,
            {
                "threadId",
                "runId",
                "state",
                "messages",
                "tools",
                "context",
                "forwardedProps",
            },
        )

    def test_delete_thread_removes_langgraph_checkpoint_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "agent_state.db"
            self._seed_checkpoint_db(db_path)
            server._settings = Settings(
                internal_api_key="test-internal-key",
                agent_state_db_path=str(db_path),
            )

            response = self.client.delete(
                "/threads/thread-a",
                headers={"Authorization": "Bearer test-internal-key"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {
                    "ok": True,
                    "thread_id": "thread-a",
                    "deleted_writes": 2,
                    "deleted_checkpoints": 1,
                },
            )
            self.assertEqual(self._row_count(db_path, "writes", "thread-a"), 0)
            self.assertEqual(
                self._row_count(db_path, "checkpoints", "thread-a"),
                0,
            )
            self.assertEqual(self._row_count(db_path, "writes", "thread-b"), 1)
            self.assertEqual(
                self._row_count(db_path, "checkpoints", "thread-b"),
                1,
            )

    @staticmethod
    def _row_count(db_path: Path, table_name: str, thread_id: str) -> int:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()

        return int(row[0]) if row else 0

    @staticmethod
    def _seed_checkpoint_db(db_path: Path) -> None:
        with sqlite3.connect(db_path) as connection:
            connection.execute("CREATE TABLE writes (thread_id TEXT)")
            connection.execute("CREATE TABLE checkpoints (thread_id TEXT)")
            connection.executemany(
                "INSERT INTO writes(thread_id) VALUES (?)",
                [("thread-a",), ("thread-a",), ("thread-b",)],
            )
            connection.executemany(
                "INSERT INTO checkpoints(thread_id) VALUES (?)",
                [("thread-a",), ("thread-b",)],
            )
            connection.commit()


if __name__ == "__main__":
    unittest.main()
