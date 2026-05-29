import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

import copilot.agent_app as agent_app
from copilot.settings import Settings


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


class AgentAppRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._original_lifespan_context = agent_app.app.router.lifespan_context
        agent_app.app.router.lifespan_context = _noop_lifespan

    @classmethod
    def tearDownClass(cls) -> None:
        agent_app.app.router.lifespan_context = cls._original_lifespan_context

    def setUp(self) -> None:
        self._original_settings = agent_app._settings
        self._original_agent = agent_app._agent
        self._original_graph = agent_app._graph
        self._original_checkpointer = agent_app._checkpointer
        self._original_thread_run_locks = agent_app._thread_run_locks
        agent_app._thread_run_locks = {}
        self.client = TestClient(agent_app.app)

    def tearDown(self) -> None:
        self.client.close()
        agent_app._settings = self._original_settings
        agent_app._agent = self._original_agent
        agent_app._graph = self._original_graph
        agent_app._checkpointer = self._original_checkpointer
        agent_app._thread_run_locks = self._original_thread_run_locks

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

    def test_lifespan_exposes_compiled_graph_to_voice_handlers(self) -> None:
        class FakeGraph:
            def __init__(self) -> None:
                self.configs: list[dict] = []

            def with_config(self, **config):
                self.configs.append(config)
                return self

        class FakeSaverContext:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, *_args):
                return False

        fake_graph = FakeGraph()
        fake_settings = Settings(agent_state_db_path=":memory:", jobs_enabled=False)

        async def exercise() -> None:
            with (
                patch.object(agent_app, "Settings", return_value=fake_settings),
                patch.object(agent_app, "init_thread_store"),
                patch.object(agent_app, "_make_llm", return_value=object()),
                patch.object(
                    agent_app.AsyncSqliteSaver,
                    "from_conn_string",
                    return_value=FakeSaverContext(),
                ),
                patch.object(agent_app, "CachingCheckpointSaver", return_value=object()),
                patch.object(agent_app, "build_graph", return_value=fake_graph),
                patch.object(agent_app, "LangGraphAGUIAgent", return_value=object()),
                patch.object(agent_app.speech_pipelines, "configure"),
                patch.object(agent_app.speech_pipelines, "stop_all", AsyncMock()),
                patch.object(
                    agent_app,
                    "_flush_pending_checkpoints_on_shutdown",
                    AsyncMock(),
                ),
            ):
                async with agent_app.lifespan(agent_app.app):
                    self.assertIs(agent_app._graph, fake_graph)

        asyncio.run(exercise())

    def test_media_rtc_configuration_includes_ice_gather_timeout(self) -> None:
        agent_app._settings = Settings(
            internal_api_key="test-internal-key",
            media_rtc_configuration='{"iceServers":[]}',
            media_ice_gather_timeout_ms=500,
        )

        response = self.client.get(
            "/media/rtc-configuration",
            headers={"Authorization": "Bearer test-internal-key"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "iceServers": [],
                "iceGatherTimeoutMs": 500,
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
            agent_app._settings = Settings(
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

    def test_ag_ui_proxy_flushes_only_the_active_thread(self) -> None:
        class FakeAgent:
            async def run(self, _input_data):
                yield {"event": "done"}

        class FakeCheckpointer:
            def __init__(self) -> None:
                self.flush_calls: list[str | None] = []

            async def flush(self, thread_id: str | None = None) -> None:
                self.flush_calls.append(thread_id)

            async def pending_thread_ids(self) -> list[str | None]:
                return []

        fake_checkpointer = FakeCheckpointer()
        agent_app._agent = FakeAgent()
        agent_app._checkpointer = fake_checkpointer

        async def collect_events():
            proxy = agent_app._AGUIAgentProxy()
            return [event async for event in proxy.run({"threadId": "thread-a"})]

        events = asyncio.run(collect_events())

        self.assertEqual(events, [{"event": "done"}])
        self.assertEqual(fake_checkpointer.flush_calls, ["thread-a"])

    def test_voice_transcript_submission_invokes_graph_with_thread_lock(self) -> None:
        class FakeGraph:
            def __init__(self) -> None:
                self.calls: list[tuple[dict, dict]] = []

            async def ainvoke(self, input_data, config):
                self.calls.append((input_data, config))
                await asyncio.sleep(0.01)
                return {
                    "messages": [AIMessage(content=f"reply to {input_data['messages'][0].content}")]
                }

        class FakeCheckpointer:
            def __init__(self) -> None:
                self.flush_calls: list[str | None] = []

            async def flush(self, thread_id: str | None = None) -> None:
                self.flush_calls.append(thread_id)

        fake_graph = FakeGraph()
        fake_checkpointer = FakeCheckpointer()
        agent_app._graph = fake_graph
        agent_app._checkpointer = fake_checkpointer

        async def submit_twice():
            return await asyncio.gather(
                agent_app._submit_voice_transcript_to_chat("thread-a", "first"),
                agent_app._submit_voice_transcript_to_chat("thread-a", "second"),
            )

        results = asyncio.run(submit_twice())

        self.assertEqual(len(fake_graph.calls), 2)
        self.assertEqual(
            [call[1] for call in fake_graph.calls],
            [
                {"configurable": {"thread_id": "thread-a"}},
                {"configurable": {"thread_id": "thread-a"}},
            ],
        )
        self.assertEqual(
            [call[0]["messages"][0].content for call in fake_graph.calls],
            ["first", "second"],
        )
        self.assertEqual(results, ["reply to first", "reply to second"])
        self.assertEqual(fake_checkpointer.flush_calls, ["thread-a", "thread-a"])

    def test_voice_transcript_submission_cancels_graph_invocation(self) -> None:
        class FakeGraph:
            def __init__(self) -> None:
                self.started = asyncio.Event()
                self.cancelled = asyncio.Event()

            async def ainvoke(self, _input_data, config):
                self.started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.cancelled.set()
                    raise

        class FakeCheckpointer:
            async def flush(self, thread_id: str | None = None) -> None:
                return None

        fake_graph = FakeGraph()
        agent_app._graph = fake_graph
        agent_app._checkpointer = FakeCheckpointer()

        async def exercise():
            task = asyncio.create_task(
                agent_app._submit_voice_transcript_to_chat("thread-a", "cancel me")
            )
            await asyncio.wait_for(fake_graph.started.wait(), timeout=1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(fake_graph.cancelled.wait(), timeout=1)

        asyncio.run(exercise())

    def test_voice_transcript_streaming_yields_semantic_chunks(self) -> None:
        class FakeGraph:
            def __init__(self) -> None:
                self.calls: list[tuple[dict, dict, str]] = []

            async def astream(self, input_data, config, stream_mode):
                self.calls.append((input_data, config, stream_mode))
                yield (
                    AIMessageChunk(content='{"intent":"chat"}'),
                    {"langgraph_node": "router"},
                )
                yield (
                    AIMessageChunk(content="The living room light is now on. "),
                    {"langgraph_node": "respond"},
                )
                yield (
                    AIMessageChunk(content="I left the hallway unchanged."),
                    {"langgraph_node": "respond"},
                )

        class FakeCheckpointer:
            def __init__(self) -> None:
                self.flush_calls: list[str | None] = []

            async def flush(self, thread_id: str | None = None) -> None:
                self.flush_calls.append(thread_id)

        fake_graph = FakeGraph()
        fake_checkpointer = FakeCheckpointer()
        agent_app._graph = fake_graph
        agent_app._checkpointer = fake_checkpointer

        async def collect_chunks():
            return [
                chunk
                async for chunk in agent_app._stream_voice_transcript_to_chat(
                    "thread-a",
                    "turn on the light",
                )
            ]

        chunks = asyncio.run(collect_chunks())

        self.assertEqual(
            chunks,
            ["The living room light is now on.", "I left the hallway unchanged."],
        )
        self.assertEqual(len(fake_graph.calls), 1)
        self.assertEqual(fake_graph.calls[0][2], "messages")
        self.assertEqual(fake_checkpointer.flush_calls, ["thread-a"])

    def test_voice_transcript_streaming_cancels_graph_stream(self) -> None:
        class FakeGraph:
            def __init__(self) -> None:
                self.started = asyncio.Event()
                self.cancelled = asyncio.Event()

            async def astream(self, _input_data, config, stream_mode):
                self.started.set()
                try:
                    await asyncio.Event().wait()
                    yield (
                        AIMessageChunk(content="unreachable"),
                        {"langgraph_node": "respond"},
                    )
                except asyncio.CancelledError:
                    self.cancelled.set()
                    raise

        class FakeCheckpointer:
            def __init__(self) -> None:
                self.flush_calls: list[str | None] = []

            async def flush(self, thread_id: str | None = None) -> None:
                self.flush_calls.append(thread_id)

        fake_graph = FakeGraph()
        fake_checkpointer = FakeCheckpointer()
        agent_app._graph = fake_graph
        agent_app._checkpointer = fake_checkpointer

        async def exercise():
            async def collect():
                return [
                    chunk
                    async for chunk in agent_app._stream_voice_transcript_to_chat(
                        "thread-a",
                        "cancel me",
                    )
                ]

            task = asyncio.create_task(collect())
            await asyncio.wait_for(fake_graph.started.wait(), timeout=1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(fake_graph.cancelled.wait(), timeout=1)

        asyncio.run(exercise())

        self.assertEqual(fake_checkpointer.flush_calls, ["thread-a"])

    def test_ag_ui_proxy_skips_persistence_for_embed_ephemeral_threads(self) -> None:
        class FakeAgent:
            async def run(self, _input_data):
                yield {"event": "done"}

        class FakeCheckpointer:
            def __init__(self) -> None:
                self.flush_calls: list[str | None] = []

            async def flush(self, thread_id: str | None = None) -> None:
                self.flush_calls.append(thread_id)

            async def pending_thread_ids(self) -> list[str | None]:
                return []

        fake_checkpointer = FakeCheckpointer()
        agent_app._agent = FakeAgent()
        agent_app._checkpointer = fake_checkpointer

        async def collect_events():
            proxy = agent_app._AGUIAgentProxy()
            return [event async for event in proxy.run({"threadId": "embed-ephemeral-thread-a"})]

        events = asyncio.run(collect_events())

        self.assertEqual(events, [{"event": "done"}])
        self.assertEqual(fake_checkpointer.flush_calls, [])

    def test_persistence_operation_survives_cancellation(self) -> None:
        class OperationProbe:
            def __init__(self) -> None:
                self.started = asyncio.Event()
                self.release = asyncio.Event()
                self.completed = asyncio.Event()

            async def run(self) -> None:
                self.started.set()
                await self.release.wait()
                self.completed.set()

        async def exercise() -> None:
            probe = OperationProbe()
            task = asyncio.create_task(
                agent_app._run_persistence_operation(
                    probe.run(),
                    error_message="probe failed",
                )
            )

            await asyncio.wait_for(probe.started.wait(), timeout=1)
            task.cancel()
            probe.release.set()

            cancelled = await asyncio.wait_for(task, timeout=1)
            self.assertTrue(cancelled)
            await asyncio.wait_for(probe.completed.wait(), timeout=1)

        asyncio.run(exercise())

    def test_shutdown_flushes_pending_checkpoints(self) -> None:
        class FakeCheckpointer:
            def __init__(self) -> None:
                self.flush_calls: list[str | None] = []
                self.deleted_threads: list[str] = []

            async def flush(self, thread_id: str | None = None) -> None:
                self.flush_calls.append(thread_id)

            async def pending_thread_ids(self) -> list[str | None]:
                return ["embed-ephemeral-thread-a", "thread-b"]

            async def adelete_thread(self, thread_id: str) -> None:
                self.deleted_threads.append(thread_id)

        fake_checkpointer = FakeCheckpointer()
        agent_app._checkpointer = fake_checkpointer

        asyncio.run(agent_app._flush_pending_checkpoints_on_shutdown())

        self.assertEqual(fake_checkpointer.deleted_threads, ["embed-ephemeral-thread-a"])

    def test_delete_thread_uses_checkpointer_when_available(self) -> None:
        class FakeCheckpointer:
            def __init__(self, db_path: Path) -> None:
                self.db_path = db_path
                self.deleted_threads: list[str] = []

            async def adelete_thread(self, thread_id: str) -> None:
                self.deleted_threads.append(thread_id)
                with sqlite3.connect(self.db_path) as connection:
                    connection.execute(
                        "DELETE FROM writes WHERE thread_id = ?",
                        (thread_id,),
                    )
                    connection.execute(
                        "DELETE FROM checkpoints WHERE thread_id = ?",
                        (thread_id,),
                    )
                    connection.commit()

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "agent_state.db"
            self._seed_checkpoint_db(db_path)
            agent_app._settings = Settings(
                internal_api_key="test-internal-key",
                agent_state_db_path=str(db_path),
            )
            agent_app._checkpointer = FakeCheckpointer(db_path)

            response = self.client.delete(
                "/threads/thread-a",
                headers={"Authorization": "Bearer test-internal-key"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(agent_app._checkpointer.deleted_threads, ["thread-a"])
            self.assertEqual(self._row_count(db_path, "writes", "thread-a"), 0)
            self.assertEqual(self._row_count(db_path, "checkpoints", "thread-a"), 0)

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
