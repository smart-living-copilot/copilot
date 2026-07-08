import asyncio
import logging
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

import wotbot.api.main as wotbot_app
from wotbot.core.settings import Settings


def _enable_log_capture(logger_name: str) -> None:
    logging.disable(logging.NOTSET)
    logging.getLogger(logger_name).disabled = False


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


class AgentAppRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._original_lifespan_context = wotbot_app.app.router.lifespan_context
        wotbot_app.app.router.lifespan_context = _noop_lifespan

    @classmethod
    def tearDownClass(cls) -> None:
        wotbot_app.app.router.lifespan_context = cls._original_lifespan_context

    def setUp(self) -> None:
        self._original_settings = wotbot_app.agui_runtime.settings
        self._original_agent = wotbot_app.agui_runtime.agent
        self._original_checkpointer = wotbot_app.agui_runtime.checkpointer
        self._original_thread_run_locks = wotbot_app.agui_runtime._thread_run_locks
        self._original_app_state = dict(wotbot_app.app.state._state)
        wotbot_app.agui_runtime._thread_run_locks = {}
        self.client = TestClient(wotbot_app.app)

    def tearDown(self) -> None:
        self.client.close()
        wotbot_app.agui_runtime.settings = self._original_settings
        wotbot_app.agui_runtime.agent = self._original_agent
        wotbot_app.agui_runtime.checkpointer = self._original_checkpointer
        wotbot_app.agui_runtime._thread_run_locks = self._original_thread_run_locks
        wotbot_app.app.state._state.clear()
        wotbot_app.app.state._state.update(self._original_app_state)

    def _set_settings(self, settings: Settings) -> None:
        wotbot_app.agui_runtime.configure(settings=settings)
        wotbot_app.app.state.settings = settings

    def test_ag_ui_health_route_reports_agent_name(self) -> None:
        response = self.client.get("/ag-ui/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "agent": {
                    "name": "wotbot",
                },
            },
        )

    def test_lifespan_exposes_compiled_graph(self) -> None:
        class FakeGraph:
            def __init__(self) -> None:
                self.configs: list[dict] = []

            def with_config(self, **config):
                self.configs.append(config)
                return self

        class FakeSaverContext:
            async def __aenter__(self):
                return fake_saver

            async def __aexit__(self, *_args):
                return False

        fake_saver = object()
        fake_graph = FakeGraph()
        fake_settings = Settings(agent_handoff_enabled=True)
        fake_job_service = AsyncMock()

        async def exercise() -> None:
            with (
                patch.object(wotbot_app, "AgentSettings", return_value=fake_settings),
                patch.object(wotbot_app, "init_db"),
                patch.object(wotbot_app, "get_registry_settings"),
                patch.object(wotbot_app, "get_connection_pool", return_value=object()),
                patch.object(wotbot_app, "start_backend_runtime", AsyncMock()),
                patch.object(wotbot_app, "shutdown_backend_runtime", AsyncMock()),
                patch.object(wotbot_app, "make_llm", return_value=object()),
                patch.object(
                    wotbot_app, "_checkpoint_saver_context", return_value=FakeSaverContext()
                ),
                patch.object(wotbot_app, "build_graph", return_value=fake_graph) as build_graph,
                patch.object(wotbot_app, "LangGraphAGUIAgent", return_value=object()),
                patch.object(wotbot_app, "JobService", return_value=fake_job_service),
                patch.object(wotbot_app, "set_active_job_service"),
            ):
                async with wotbot_app.lifespan(wotbot_app.app):
                    self.assertIs(wotbot_app.app.state.graph, fake_graph)
                    self.assertIs(build_graph.call_args.kwargs["checkpointer"], fake_saver)
                    self.assertTrue(build_graph.call_args.kwargs["handoff_enabled"])
                    fake_job_service.start.assert_awaited_once()
                fake_job_service.stop.assert_awaited_once()

        asyncio.run(exercise())

    def test_configure_logging_forces_uvicorn_logging_setup(self) -> None:
        loggers: dict[str | None, Mock] = {}

        def fake_get_logger(name: str | None = None) -> Mock:
            logger = Mock()
            loggers[name] = logger
            return logger

        with (
            patch.object(wotbot_app.logging, "basicConfig") as basic_config,
            patch.object(
                wotbot_app.logging,
                "getLogger",
                side_effect=fake_get_logger,
            ),
        ):
            wotbot_app.configure_logging("DEBUG")

        basic_config.assert_called_once_with(
            level="DEBUG",
            format=wotbot_app.LOG_FORMAT,
            force=True,
        )
        for logger_name in ("wotbot", "uvicorn", "uvicorn.error", "uvicorn.access"):
            loggers[logger_name].setLevel.assert_called_once_with("DEBUG")

    def test_livekit_token_endpoint_reports_disabled_when_unconfigured(self) -> None:
        self._set_settings(Settings(internal_api_key="test-internal-key"))

        response = self.client.post(
            "/media/livekit/token",
            json={"threadId": "thread-a"},
            headers={"Authorization": "Bearer test-internal-key"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"enabled": False})

    def test_legacy_media_endpoints_are_removed(self) -> None:
        self._set_settings(Settings(internal_api_key="test-internal-key"))

        rtc_response = self.client.get(
            "/media/rtc-configuration",
            headers={"Authorization": "Bearer test-internal-key"},
        )
        offer_response = self.client.post(
            "/media/webrtc/offer",
            json={},
            headers={"Authorization": "Bearer test-internal-key"},
        )

        self.assertEqual(rtc_response.status_code, 404)
        self.assertEqual(offer_response.status_code, 404)

    def test_livekit_token_endpoint_creates_connection_details(self) -> None:
        class FakeLiveKitDetails:
            def as_response(self):
                return {
                    "enabled": True,
                    "url": "ws://livekit:7880",
                    "token": "token-a",
                    "room": "wotbot-thread-a",
                    "participantIdentity": "web-a",
                    "agentName": "wotbot",
                    "expiresInSeconds": 600,
                }

        settings = Settings(
            internal_api_key="test-internal-key",
            livekit_url="ws://livekit:7880",
            livekit_public_url="ws://localhost:7880",
            livekit_api_key="devkey",
            livekit_api_secret="secret",
        )
        self._set_settings(settings)

        with patch(
            "wotbot.media.routes.create_livekit_connection_details",
            return_value=FakeLiveKitDetails(),
        ) as create_details:
            response = self.client.post(
                "/media/livekit/token",
                json={"threadId": "thread-a"},
                headers={"Authorization": "Bearer test-internal-key"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["token"], "token-a")
        create_details.assert_called_once_with(settings, thread_id="thread-a")

    def test_livekit_dispatch_endpoint_dispatches_agent(self) -> None:
        settings = Settings(
            internal_api_key="test-internal-key",
            livekit_url="ws://livekit:7880",
            livekit_api_key="devkey",
            livekit_api_secret="secret",
        )
        self._set_settings(settings)

        with patch("wotbot.media.routes.dispatch_livekit_agent") as dispatch_agent:
            response = self.client.post(
                "/media/livekit/dispatch",
                json={
                    "room": "wotbot-thread-a-session-a",
                    "threadId": "thread-a",
                    "participantIdentity": "web-a",
                },
                headers={"Authorization": "Bearer test-internal-key"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"enabled": True, "dispatched": True})
        dispatch_agent.assert_awaited_once_with(
            settings,
            room="wotbot-thread-a-session-a",
            thread_id="thread-a",
            participant_identity="web-a",
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
        self._set_settings(Settings(internal_api_key="test-internal-key"))

        with patch("wotbot.threads.routes.delete_thread_metadata", return_value=True):
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
                "deleted": True,
            },
        )

    def test_ag_ui_proxy_runs_active_thread(self) -> None:
        _enable_log_capture("wotbot.core.agui_runtime")

        class FakeAgent:
            async def run(self, _input_data):
                yield {"event": "done"}

        wotbot_app.agui_runtime.configure(agent=FakeAgent())

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [event async for event in proxy.run({"threadId": "thread-a", "runId": "run-a"})]

        with self.assertLogs("wotbot.core.agui_runtime", level="INFO") as logs:
            events = asyncio.run(collect_events())

        self.assertEqual(events, [{"event": "done"}])
        output = "\n".join(logs.output)
        self.assertIn("AG-UI run started thread_id=thread-a run_id=run-a", output)
        self.assertIn("uses_thread_lock=True", output)
        self.assertIn("AG-UI run finished thread_id=thread-a run_id=run-a", output)

    def test_ag_ui_proxy_logs_agent_failure(self) -> None:
        _enable_log_capture("wotbot.core.agui_runtime")

        class FakeAgent:
            async def run(self, _input_data):
                if False:
                    yield {"event": "unused"}
                raise RuntimeError("agent boom")

        wotbot_app.agui_runtime.configure(agent=FakeAgent())

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [event async for event in proxy.run({"threadId": "thread-a", "runId": "run-a"})]

        with self.assertLogs("wotbot.core.agui_runtime", level="ERROR") as logs:
            with self.assertRaises(RuntimeError):
                asyncio.run(collect_events())

        output = "\n".join(logs.output)
        self.assertIn("AG-UI run failed thread_id=thread-a run_id=run-a", output)
        self.assertIn("RuntimeError: agent boom", output)

    def test_ag_ui_proxy_cleans_up_embed_ephemeral_checkpoints(self) -> None:
        class FakeAgent:
            async def run(self, _input_data):
                yield {"event": "done"}

        class FakeCheckpointer:
            def __init__(self) -> None:
                self.deleted_threads: list[str] = []

            async def adelete_thread(self, thread_id: str) -> None:
                self.deleted_threads.append(thread_id)

        fake_checkpointer = FakeCheckpointer()
        wotbot_app.agui_runtime.configure(
            agent=FakeAgent(),
            checkpointer=fake_checkpointer,
        )

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [event async for event in proxy.run({"threadId": "embed-ephemeral-thread-a"})]

        events = asyncio.run(collect_events())

        self.assertEqual(events, [{"event": "done"}])
        self.assertEqual(fake_checkpointer.deleted_threads, ["embed-ephemeral-thread-a"])

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
                wotbot_app.agui_runtime.run_persistence_operation(
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

    def test_delete_thread_uses_checkpointer_when_available(self) -> None:
        class FakeCheckpointer:
            def __init__(self) -> None:
                self.deleted_threads: list[str] = []

            async def adelete_thread(self, thread_id: str) -> None:
                self.deleted_threads.append(thread_id)

        self._set_settings(Settings(internal_api_key="test-internal-key"))
        wotbot_app.agui_runtime.configure(checkpointer=FakeCheckpointer())

        with patch("wotbot.threads.routes.delete_thread_metadata", return_value=True):
            response = self.client.delete(
                "/threads/thread-a",
                headers={"Authorization": "Bearer test-internal-key"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(wotbot_app.agui_runtime.checkpointer.deleted_threads, ["thread-a"])


if __name__ == "__main__":
    unittest.main()
