import asyncio
import logging
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

import wotbot.api.main as wotbot_app
from wotbot.core.settings import Settings


def _enable_log_capture(logger_name: str) -> None:
    logging.disable(logging.NOTSET)
    logging.getLogger(logger_name).disabled = False


class _FakeGraph:
    """Minimal stand-in for a compiled LangGraph graph. Unlike a plain fixed
    snapshot, aupdate_state actually mutates what aget_state subsequently
    returns -- matching the real checkpointer closely enough that the
    finalizer's two call sites (proactive, at the top of run(); reactive, in
    its finally) see each other's work instead of redundantly re-finalizing
    already-clean state."""

    def __init__(self, messages: list) -> None:
        self.state = SimpleNamespace(values={"messages": list(messages)})
        self.update_calls: list[dict] = []

    async def aget_state(self, _config):
        return self.state

    async def aupdate_state(self, _config, update, **_kwargs):
        self.update_calls.append(update)
        self.state.values["messages"].extend(update.get("messages", []))


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
        self._original_agent_factory = wotbot_app.agui_runtime.agent_factory
        self._original_checkpointer = wotbot_app.agui_runtime.checkpointer
        self._original_graph = wotbot_app.agui_runtime.graph
        self._original_thread_run_locks = wotbot_app.agui_runtime._thread_run_locks
        self._original_app_state = dict(wotbot_app.app.state._state)
        wotbot_app.agui_runtime._thread_run_locks = {}
        self.client = TestClient(wotbot_app.app)

    def tearDown(self) -> None:
        self.client.close()
        wotbot_app.agui_runtime.settings = self._original_settings
        wotbot_app.agui_runtime.agent_factory = self._original_agent_factory
        wotbot_app.agui_runtime.checkpointer = self._original_checkpointer
        wotbot_app.agui_runtime.graph = self._original_graph
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
        fake_agents: list[SimpleNamespace] = []
        fake_settings = Settings(agent_handoff_enabled=True)
        fake_job_service = AsyncMock()

        def create_fake_agent(**_kwargs) -> SimpleNamespace:
            fake_agent = SimpleNamespace()
            fake_agents.append(fake_agent)
            return fake_agent

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
                patch.object(wotbot_app, "LangGraphAGUIAgent", side_effect=create_fake_agent),
                patch.object(wotbot_app, "JobService", return_value=fake_job_service),
                patch.object(wotbot_app, "set_active_job_service"),
            ):
                async with wotbot_app.lifespan(wotbot_app.app):
                    self.assertIs(wotbot_app.app.state.graph, fake_graph)
                    self.assertIs(build_graph.call_args.kwargs["checkpointer"], fake_saver)
                    self.assertTrue(build_graph.call_args.kwargs["handoff_enabled"])
                    first_agent = wotbot_app.agui_runtime.create_request_agent()
                    second_agent = wotbot_app.agui_runtime.create_request_agent()
                    self.assertIsNot(first_agent, second_agent)
                    self.assertEqual(fake_agents, [first_agent, second_agent])
                    self.assertIs(first_agent.emit_raw_events, False)
                    self.assertIs(second_agent.emit_raw_events, False)
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

        wotbot_app.agui_runtime.configure(agent_factory=FakeAgent)

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

    def test_ag_ui_proxy_isolates_agent_state_across_concurrent_threads(self) -> None:
        created_agents: list[object] = []

        async def exercise() -> list[list[SimpleNamespace]]:
            both_started = asyncio.Event()
            started_count = 0

            class StatefulFakeAgent:
                def __init__(self) -> None:
                    self.active_step: str | None = None
                    created_agents.append(self)

                async def run(self, input_data):
                    nonlocal started_count
                    self.active_step = input_data["state"]["step"]
                    yield SimpleNamespace(type="STEP_STARTED", step_name=self.active_step)
                    started_count += 1
                    if started_count == 2:
                        both_started.set()
                    await asyncio.wait_for(both_started.wait(), timeout=1)
                    yield SimpleNamespace(type="STEP_FINISHED", step_name=self.active_step)

            wotbot_app.agui_runtime.configure(agent_factory=StatefulFakeAgent)

            async def collect(thread_id: str, step: str):
                proxy = wotbot_app.agui_runtime.create_agent_proxy()
                return [
                    event
                    async for event in proxy.run(
                        {
                            "threadId": thread_id,
                            "runId": f"run-{thread_id}",
                            "state": {"step": step},
                        }
                    )
                ]

            return await asyncio.gather(
                collect("thread-a", "router"),
                collect("thread-b", "control_llm"),
            )

        event_sequences = asyncio.run(exercise())

        self.assertEqual(len(created_agents), 2)
        self.assertEqual(
            [[event.step_name for event in events] for events in event_sequences],
            [["router", "router"], ["control_llm", "control_llm"]],
        )

    def test_ag_ui_proxy_prefers_forwarded_reasoning_effort_over_stale_state(self) -> None:
        received_inputs: list[dict] = []

        class FakeAgent:
            async def run(self, input_data):
                received_inputs.append(input_data)
                yield {"event": "done"}

        wotbot_app.agui_runtime.configure(agent_factory=FakeAgent)

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [
                event
                async for event in proxy.run(
                    {
                        "threadId": "thread-a",
                        "runId": "run-a",
                        "state": {"reasoning_effort": "high", "intent": "chat"},
                        "forwardedProps": {"reasoningEffort": "low"},
                    }
                )
            ]

        events = asyncio.run(collect_events())

        self.assertEqual(events, [{"event": "done"}])
        self.assertEqual(
            received_inputs[0]["state"],
            {"reasoning_effort": "low", "intent": "chat"},
        )

    def test_ag_ui_proxy_logs_agent_failure(self) -> None:
        _enable_log_capture("wotbot.core.agui_runtime")

        class FakeAgent:
            async def run(self, _input_data):
                if False:
                    yield {"event": "unused"}
                raise RuntimeError("agent boom")

        wotbot_app.agui_runtime.configure(agent_factory=FakeAgent)

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [event async for event in proxy.run({"threadId": "thread-a", "runId": "run-a"})]

        with self.assertLogs("wotbot.core.agui_runtime", level="ERROR") as logs:
            with self.assertRaises(RuntimeError):
                asyncio.run(collect_events())

        output = "\n".join(logs.output)
        self.assertIn("AG-UI run failed thread_id=thread-a run_id=run-a", output)
        self.assertIn("RuntimeError: agent boom", output)

    def test_ag_ui_proxy_finalizes_dangling_human_turn_after_a_failed_run(self) -> None:
        """A run that dies before producing a response (aborted, or a real
        error) must not leave the checkpoint's last message as a bare
        HumanMessage -- see AguiRuntime._finalize_interrupted_run for why:
        every future reconnect to the thread would find that same unfinished
        turn and reattempt (and re-fail) it.

        The dangling message only appears once this run's own agent.run()
        merges it in (a FakeAgent stand-in for what the real merge_state
        does internally) -- the thread starts clean, so this exercises the
        REACTIVE finalize (in run()'s finally), not the proactive one."""
        fake_graph = _FakeGraph([])

        class FakeAgent:
            async def run(self, _input_data):
                fake_graph.state.values["messages"].append(
                    HumanMessage(content="write me a long poem")
                )
                if False:
                    yield {"event": "unused"}
                raise RuntimeError("agent boom")

        wotbot_app.agui_runtime.configure(agent_factory=FakeAgent, graph=fake_graph)

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [event async for event in proxy.run({"threadId": "thread-a", "runId": "run-a"})]

        with self.assertRaises(RuntimeError):
            asyncio.run(collect_events())

        self.assertEqual(len(fake_graph.update_calls), 1)
        appended = fake_graph.update_calls[0]["messages"]
        self.assertEqual(len(appended), 1)
        self.assertIsInstance(appended[0], AIMessage)
        self.assertIn("interrupted", appended[0].content)

    def test_ag_ui_proxy_does_not_touch_an_already_answered_turn(self) -> None:
        """If the checkpoint's last message is already an AI response (the
        failure happened elsewhere, e.g. a post-response persistence step),
        there's nothing dangling to finalize -- don't append a spurious
        notice after a real answer."""
        fake_graph = _FakeGraph(
            [
                HumanMessage(content="write me a poem"),
                AIMessage(content="Roses are red..."),
            ]
        )

        class FakeAgent:
            async def run(self, _input_data):
                if False:
                    yield {"event": "unused"}
                raise RuntimeError("agent boom")

        wotbot_app.agui_runtime.configure(agent_factory=FakeAgent, graph=fake_graph)

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [event async for event in proxy.run({"threadId": "thread-a", "runId": "run-a"})]

        with self.assertRaises(RuntimeError):
            asyncio.run(collect_events())

        self.assertEqual(fake_graph.update_calls, [])

    def test_ag_ui_proxy_does_not_finalize_a_completed_run(self) -> None:
        """A run that finishes normally, starting from a clean thread (no
        dangling turn to begin with), must never trigger the
        interrupted-turn finalizer."""
        fake_graph = _FakeGraph([])

        class FakeAgent:
            async def run(self, _input_data):
                yield {"event": "done"}

        wotbot_app.agui_runtime.configure(agent_factory=FakeAgent, graph=fake_graph)

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [event async for event in proxy.run({"threadId": "thread-a", "runId": "run-a"})]

        events = asyncio.run(collect_events())

        self.assertEqual(events, [{"event": "done"}])
        self.assertEqual(fake_graph.update_calls, [])

    def test_ag_ui_proxy_finalizes_dangling_turn_after_real_cancellation(self) -> None:
        """The literal reported scenario: a genuine asyncio cancellation
        (stop button, closed tab, dropped connection) mid-run -- not a
        simulated exception -- must still finalize the dangling turn."""
        fake_graph = _FakeGraph([])

        class FakeAgent:
            def __init__(self) -> None:
                self.started = asyncio.Event()
                self.release = asyncio.Event()

            async def run(self, _input_data):
                fake_graph.state.values["messages"].append(
                    HumanMessage(content="write me a long poem")
                )
                self.started.set()
                await self.release.wait()
                yield {"event": "unused"}

        fake_agent = FakeAgent()
        wotbot_app.agui_runtime.configure(agent_factory=lambda: fake_agent, graph=fake_graph)

        async def exercise() -> None:
            proxy = wotbot_app.agui_runtime.create_agent_proxy()

            async def drain() -> None:
                async for _event in proxy.run({"threadId": "thread-a", "runId": "run-a"}):
                    pass

            task = asyncio.create_task(drain())
            await asyncio.wait_for(fake_agent.started.wait(), timeout=1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        asyncio.run(exercise())

        self.assertEqual(len(fake_graph.update_calls), 1)
        appended = fake_graph.update_calls[0]["messages"]
        self.assertIsInstance(appended[0], AIMessage)
        self.assertIn("interrupted", appended[0].content)

    def test_ag_ui_proxy_proactively_heals_a_turn_left_dangling_by_a_prior_run(self) -> None:
        """The race actually reported: a previous run's reactive finalize
        runs in a background task (specifically so a cancellation can't kill
        it -- see run_persistence_operation) and isn't guaranteed to finish
        before the user immediately reconnects/retries. A brand new run
        starting against a thread that's still dangling from an earlier,
        never-cleaned-up failure must heal it before proceeding -- even
        though this new run itself succeeds normally."""
        fake_graph = _FakeGraph([HumanMessage(content="write me a long poem")])

        class FakeAgent:
            async def run(self, _input_data):
                yield {"event": "done"}

        wotbot_app.agui_runtime.configure(agent_factory=FakeAgent, graph=fake_graph)

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [event async for event in proxy.run({"threadId": "thread-a", "runId": "run-a"})]

        events = asyncio.run(collect_events())

        self.assertEqual(events, [{"event": "done"}])
        self.assertEqual(len(fake_graph.update_calls), 1)
        appended = fake_graph.update_calls[0]["messages"]
        self.assertIsInstance(appended[0], AIMessage)
        self.assertIn("interrupted", appended[0].content)

    def test_ag_ui_proxy_persists_partial_text_streamed_before_the_interruption(self) -> None:
        """Stopping mid-answer should keep the truncated answer the user was
        already watching, not replace it with a generic notice on reload."""
        fake_graph = _FakeGraph([])

        class FakeAgent:
            async def run(self, _input_data):
                fake_graph.state.values["messages"].append(HumanMessage(content="write a poem"))
                yield SimpleNamespace(type="TEXT_MESSAGE_START", message_id="m1")
                yield SimpleNamespace(
                    type="TEXT_MESSAGE_CONTENT", message_id="m1", delta="Roses are "
                )
                yield SimpleNamespace(
                    type="TEXT_MESSAGE_CONTENT", message_id="m1", delta="red, violets"
                )
                raise RuntimeError("stopped mid-answer")

        wotbot_app.agui_runtime.configure(agent_factory=FakeAgent, graph=fake_graph)

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [event async for event in proxy.run({"threadId": "thread-a", "runId": "run-a"})]

        with self.assertRaises(RuntimeError):
            asyncio.run(collect_events())

        appended = fake_graph.update_calls[0]["messages"]
        self.assertEqual(appended[0].content, "Roses are red, violets")

    def test_ag_ui_proxy_keeps_only_the_in_flight_message_as_partial_text(self) -> None:
        """The router node streams its own ``{"intent": ...}`` payload as a
        text message before the answering node starts. An interrupted turn
        must persist the answer in progress, not that earlier payload."""
        fake_graph = _FakeGraph([])

        class FakeAgent:
            async def run(self, _input_data):
                fake_graph.state.values["messages"].append(HumanMessage(content="write a poem"))
                yield SimpleNamespace(type="TEXT_MESSAGE_START", message_id="router")
                yield SimpleNamespace(
                    type="TEXT_MESSAGE_CONTENT", message_id="router", delta='{"intent":"chat"}'
                )
                yield SimpleNamespace(type="TEXT_MESSAGE_END", message_id="router")
                yield SimpleNamespace(type="TEXT_MESSAGE_START", message_id="answer")
                yield SimpleNamespace(
                    type="TEXT_MESSAGE_CONTENT", message_id="answer", delta="Roses are red"
                )
                raise RuntimeError("stopped mid-answer")

        wotbot_app.agui_runtime.configure(agent_factory=FakeAgent, graph=fake_graph)

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [event async for event in proxy.run({"threadId": "thread-a", "runId": "run-a"})]

        with self.assertRaises(RuntimeError):
            asyncio.run(collect_events())

        appended = fake_graph.update_calls[0]["messages"]
        self.assertEqual(appended[0].content, "Roses are red")
        self.assertNotIn("intent", appended[0].content)

    def test_ag_ui_proxy_ignores_a_completed_message_when_nothing_is_in_flight(self) -> None:
        """Interrupting in the gap AFTER the router's message completed but
        BEFORE the answering node starts streaming leaves no in-flight
        message at all. The router's completed ``{"intent": ...}`` payload
        must not be persisted as the assistant's reply -- fall back to the
        generic notice instead (regression: it used to be stored verbatim)."""
        fake_graph = _FakeGraph([])

        class FakeAgent:
            async def run(self, _input_data):
                fake_graph.state.values["messages"].append(HumanMessage(content="write a poem"))
                yield SimpleNamespace(type="TEXT_MESSAGE_START", message_id="router")
                yield SimpleNamespace(
                    type="TEXT_MESSAGE_CONTENT", message_id="router", delta='{"intent":"chat"}'
                )
                yield SimpleNamespace(type="TEXT_MESSAGE_END", message_id="router")
                raise RuntimeError("stopped between nodes")

        wotbot_app.agui_runtime.configure(agent_factory=FakeAgent, graph=fake_graph)

        async def collect_events():
            proxy = wotbot_app.agui_runtime.create_agent_proxy()
            return [event async for event in proxy.run({"threadId": "thread-a", "runId": "run-a"})]

        with self.assertRaises(RuntimeError):
            asyncio.run(collect_events())

        appended = fake_graph.update_calls[0]["messages"]
        self.assertNotIn("intent", appended[0].content)
        self.assertIn("interrupted", appended[0].content)

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
            agent_factory=FakeAgent,
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
