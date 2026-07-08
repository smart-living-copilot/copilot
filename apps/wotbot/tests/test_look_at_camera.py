import importlib
import unittest
from unittest.mock import patch

from wotbot.media import media_sessions, snapshot_notifiers

camera_module = importlib.import_module("wotbot.agent.tools.look_at_camera")


class LookAtCameraTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_notifies_snapshot_before_calling_vision_model(self) -> None:
        thread_id = "thread-look-at-camera-order"
        session_id = "session-look-at-camera-order"
        events: list[tuple[str, object]] = []

        async def on_snapshot(captured_at: str | None) -> None:
            events.append(("snapshot", captured_at))

        class FakeVisionLLM:
            def with_structured_output(self, _schema):
                return self

            async def ainvoke(self, messages):
                events.append(("vision", messages))
                return camera_module.CameraObservation(
                    primary_object="table lamp",
                    candidates=[],
                    scene="living room",
                    confidence="high",
                    notes="The lamp is centered.",
                )

        unregister = snapshot_notifiers.register(thread_id, on_snapshot)
        media_sessions.set_metadata(session_id, thread_id=thread_id)
        media_sessions.store_video_frame_jpeg(session_id, jpeg_bytes=b"\xff\xd8\xff\xd9")

        try:
            with (
                patch.object(camera_module._settings, "vision_enabled", True),
                patch.object(camera_module._settings, "vision_model", "vision-test-model"),
                patch.object(camera_module, "_make_vision_llm", return_value=FakeVisionLLM()),
            ):
                result = await camera_module.look_at_camera.coroutine(
                    user_hint="identify this",
                    config={"configurable": {"thread_id": thread_id}},
                )
        finally:
            unregister()
            media_sessions.close(session_id)

        self.assertEqual([event[0] for event in events], ["snapshot", "vision"])
        self.assertEqual(result["primary_object"], "table lamp")


if __name__ == "__main__":
    unittest.main()
