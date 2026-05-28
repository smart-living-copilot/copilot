import asyncio
import time
import unittest

import numpy as np

from copilot.media import (
    MediaSessionRegistry,
    SpeechPipelineManager,
    media_sessions,
    parse_rtc_configuration,
)


class MediaSessionRegistryTestCase(unittest.TestCase):
    def test_metadata_and_frame_counts_share_webrtc_session(self) -> None:
        registry = MediaSessionRegistry()

        registry.set_metadata("webrtc-a", thread_id="thread-a")
        registry.record_audio(
            "handler-a",
            webrtc_id="webrtc-a",
            sample_rate=16000,
            samples=320,
            channels=1,
        )
        registry.record_video(
            "handler-a",
            webrtc_id="webrtc-a",
            width=640,
            height=360,
        )

        sessions = registry.snapshots()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["webrtc_id"], "webrtc-a")
        self.assertEqual(sessions[0]["thread_id"], "thread-a")
        self.assertEqual(sessions[0]["audio_frames"], 1)
        self.assertEqual(sessions[0]["audio_samples"], 320)
        self.assertEqual(sessions[0]["video_frames"], 1)
        self.assertEqual(sessions[0]["video_width"], 640)
        self.assertEqual(sessions[0]["video_height"], 360)

    def test_latest_video_frame_only_returned_while_camera_active(self) -> None:
        registry = MediaSessionRegistry()
        registry.set_metadata("webrtc-a", thread_id="thread-a")
        registry.store_video_frame_jpeg(
            "handler-a", webrtc_id="webrtc-a", jpeg_bytes=b"fresh-frame"
        )

        snapshot = registry.latest_video_frame_for_thread("thread-a")
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot[0], b"fresh-frame")

        # A stale frame (camera turned off a while ago) must be rejected.
        self.assertIsNone(
            registry.latest_video_frame_for_thread("thread-a", max_age_seconds=0.0)
        )

        # A closed session must be rejected even with a recent frame.
        registry.store_video_frame_jpeg(
            "handler-a", webrtc_id="webrtc-a", jpeg_bytes=b"fresh-frame"
        )
        registry.close("handler-a", webrtc_id="webrtc-a")
        self.assertIsNone(registry.latest_video_frame_for_thread("thread-a"))

    def test_transcripts_are_attached_to_media_session(self) -> None:
        registry = MediaSessionRegistry()

        registry.set_metadata("webrtc-a", thread_id="thread-a")
        transcript_id = registry.add_transcript("handler-a", webrtc_id="webrtc-a")
        thread_id = registry.complete_transcript(
            transcript_id,
            text="turn on the light",
            webrtc_id="webrtc-a",
        )
        registry.submit_transcript(transcript_id)

        session = registry.get("webrtc-a")

        self.assertEqual(thread_id, "thread-a")
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session["transcript_count"], 1)
        self.assertEqual(session["latest_transcript_text"], "turn on the light")
        self.assertFalse(session["assistant_response_pending"])
        self.assertEqual(session["transcripts"][0]["status"], "submitted")
        self.assertEqual(session["transcripts"][0]["thread_id"], "thread-a")
        self.assertEqual(session["transcripts"][0]["text"], "turn on the light")

    def test_assistant_response_is_stored_on_media_session(self) -> None:
        registry = MediaSessionRegistry()

        registry.record_assistant_response("webrtc-a", "The light is on.")

        session = registry.get("webrtc-a")

        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session["latest_assistant_text"], "The light is on.")

    def test_assistant_response_delta_updates_latest_text(self) -> None:
        registry = MediaSessionRegistry()

        registry.record_assistant_response_delta("webrtc-a", "First sentence.")
        registry.record_assistant_response_delta(
            "webrtc-a",
            "First sentence. Second sentence.",
        )

        self.assertEqual(
            registry.latest_text_fields("webrtc-a"),
            (None, "First sentence. Second sentence.", False),
        )

    def test_completed_transcript_clears_previous_answer_and_sets_pending(self) -> None:
        registry = MediaSessionRegistry()

        registry.set_metadata("webrtc-a", thread_id="thread-a")
        registry.record_assistant_response("webrtc-a", "Old answer.")
        transcript_id = registry.add_transcript("handler-a", webrtc_id="webrtc-a")
        registry.complete_transcript(
            transcript_id,
            text="what about now",
            webrtc_id="webrtc-a",
        )

        self.assertEqual(
            registry.latest_text_fields("webrtc-a"),
            ("what about now", None, True),
        )

        registry.record_assistant_response_delta("webrtc-a", "New answer starts.")

        self.assertEqual(
            registry.latest_text_fields("webrtc-a"),
            ("what about now", "New answer starts.", False),
        )

    def test_transcript_errors_are_stored(self) -> None:
        registry = MediaSessionRegistry()

        transcript_id = registry.add_transcript("handler-a", webrtc_id="webrtc-a")
        registry.fail_transcript(transcript_id, "STT endpoint failed")

        session = registry.get("webrtc-a")

        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session["transcript_count"], 1)
        self.assertEqual(session["transcripts"][0]["status"], "failed")
        self.assertEqual(session["transcripts"][0]["error"], "STT endpoint failed")
        self.assertFalse(session["assistant_response_pending"])

    def test_parse_rtc_configuration_defaults_to_public_stun(self) -> None:
        self.assertEqual(
            parse_rtc_configuration(""),
            {"iceServers": [{"urls": "stun:stun.l.google.com:19302"}]},
        )

    def test_parse_rtc_configuration_rejects_non_object_payload(self) -> None:
        with self.assertRaises(ValueError):
            parse_rtc_configuration("[]")


class SpeechPipelineManagerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_outbound_audio_queue_drains_for_emit(self) -> None:
        manager = SpeechPipelineManager()
        frame = np.array([0.0, 0.25], dtype=np.float32)

        await manager.enqueue_output_audio("webrtc-a", frame)

        emitted = await manager.next_output_audio("webrtc-a")
        empty = await manager.next_output_audio("webrtc-a")

        self.assertIsNotNone(emitted)
        assert emitted is not None
        sample_rate, emitted_frame = emitted
        self.assertEqual(sample_rate, 24000)
        np.testing.assert_array_equal(emitted_frame, frame)
        self.assertIsNone(empty)

    async def test_interrupt_playback_clears_outbound_audio(self) -> None:
        manager = SpeechPipelineManager()
        frame = np.array([0.0, 0.25], dtype=np.float32)

        await manager.enqueue_output_audio("webrtc-a", frame)
        manager.interrupt_playback("webrtc-a")

        self.assertIsNone(await manager.next_output_audio("webrtc-a"))

    async def test_output_audio_emit_is_paced(self) -> None:
        manager = SpeechPipelineManager()
        frame = np.zeros(480, dtype=np.float32)

        await manager.enqueue_output_audio("webrtc-a", frame)
        await manager.enqueue_output_audio("webrtc-a", frame)

        first = await manager.next_output_audio("webrtc-a")
        started_at = time.monotonic()
        second = await manager.next_output_audio("webrtc-a")

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertGreaterEqual(time.monotonic() - started_at, 0.015)

    async def test_interrupt_playback_stops_paced_frame_already_taken_by_emit(self) -> None:
        manager = SpeechPipelineManager()
        frame = np.zeros(480, dtype=np.float32)

        await manager.enqueue_output_audio("webrtc-a", frame)
        await manager.enqueue_output_audio("webrtc-a", frame)
        self.assertIsNotNone(await manager.next_output_audio("webrtc-a"))

        pending_emit = asyncio.create_task(manager.next_output_audio("webrtc-a"))
        await asyncio.sleep(0.005)
        manager.interrupt_playback("webrtc-a")

        self.assertIsNone(await asyncio.wait_for(pending_emit, timeout=1))

    async def test_interrupted_tts_stream_does_not_enqueue_late_audio(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class DelayedTtsClient:
            async def stream_pcm(self, _text):
                started.set()
                await release.wait()
                yield b"\x00\x00" * 480

        manager = SpeechPipelineManager()
        manager._tts_client = DelayedTtsClient()

        task = asyncio.create_task(manager.synthesize_response("webrtc-interrupted-tts", "Hello"))
        await asyncio.wait_for(started.wait(), timeout=1)
        manager.interrupt_playback("webrtc-interrupted-tts")
        release.set()
        await asyncio.wait_for(task, timeout=1)

        self.assertIsNone(await manager.next_output_audio("webrtc-interrupted-tts"))

    def test_work_indicator_frames_are_quiet_24khz_frames(self) -> None:
        frames = SpeechPipelineManager._work_indicator_frames()

        self.assertGreater(len(frames), 0)
        self.assertTrue(all(frame.shape[0] <= 480 for frame in frames))
        self.assertLessEqual(max(float(np.max(np.abs(frame))) for frame in frames), 0.055)

    async def test_tts_failure_is_recorded_without_raising(self) -> None:
        class FailingTtsClient:
            async def stream_pcm(self, _text):
                raise RuntimeError("tts unavailable")
                yield b""

        manager = SpeechPipelineManager()
        manager._tts_client = FailingTtsClient()

        with self.assertLogs("copilot.media", level="ERROR"):
            await manager.synthesize_response("webrtc-tts-failed", "Hello")

        snapshot = media_sessions.get("webrtc-tts-failed")
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["tts_requests"], 1)
        self.assertEqual(snapshot["latest_tts_error"], "tts unavailable")
