import json
import unittest
import asyncio

import httpx
import numpy as np

from copilot.speech import (
    OpenAICompatibleSpeechToTextClient,
    OpenAICompatibleTextToSpeechClient,
    Pcm16FrameChunker,
    SemanticTextChunker,
    SpeechPipeline,
    SpeechUtterance,
    SttSettings,
    TtsSettings,
    TranscriptResult,
    VadSettings,
    VadUtteranceSegmenter,
    encode_wav,
    pcm_bytes_to_float32_frames,
)


class FakeDetector:
    def __init__(self, probabilities: list[float]) -> None:
        self._probabilities = probabilities
        self._index = 0
        self.reset_calls = 0

    def reset(self) -> None:
        self.reset_calls += 1

    def speech_probability(self, _samples) -> float:
        if self._index >= len(self._probabilities):
            return 0.0
        probability = self._probabilities[self._index]
        self._index += 1
        return probability


class VadUtteranceSegmenterTestCase(unittest.TestCase):
    def test_finalizes_after_speech_plus_silence(self) -> None:
        detector = FakeDetector([0.9, 0.9, 0.9, 0.1, 0.1])
        segmenter = VadUtteranceSegmenter(
            VadSettings(
                threshold=0.5,
                min_speech_ms=64,
                min_silence_ms=64,
                speech_pad_ms=0,
                max_utterance_ms=20000,
            ),
            detector,
        )

        utterances = segmenter.accept(np.ones(512 * 5, dtype=np.float32))

        self.assertEqual(len(utterances), 1)
        self.assertEqual(len(utterances[0].samples), 512 * 3)

    def test_ignores_short_noise_under_min_speech(self) -> None:
        detector = FakeDetector([0.9, 0.1, 0.1])
        segmenter = VadUtteranceSegmenter(
            VadSettings(
                threshold=0.5,
                min_speech_ms=64,
                min_silence_ms=64,
                speech_pad_ms=0,
                max_utterance_ms=20000,
            ),
            detector,
        )

        utterances = segmenter.accept(np.ones(512 * 3, dtype=np.float32))

        self.assertEqual(utterances, [])
        self.assertIsNone(segmenter.flush())

    def test_max_utterance_duration_forces_finalization(self) -> None:
        detector = FakeDetector([0.9, 0.9, 0.9, 0.9])
        segmenter = VadUtteranceSegmenter(
            VadSettings(
                threshold=0.5,
                min_speech_ms=32,
                min_silence_ms=1000,
                speech_pad_ms=0,
                max_utterance_ms=96,
            ),
            detector,
        )

        utterances = segmenter.accept(np.ones(512 * 4, dtype=np.float32))

        self.assertEqual(len(utterances), 1)
        self.assertEqual(len(utterances[0].samples), 512 * 3)

    def test_notifies_when_speech_starts(self) -> None:
        detector = FakeDetector([0.9, 0.9])
        starts = 0
        segmenter = VadUtteranceSegmenter(
            VadSettings(
                threshold=0.5,
                min_speech_ms=64,
                min_silence_ms=1000,
                speech_pad_ms=0,
                max_utterance_ms=20000,
            ),
            detector,
        )

        def on_speech_started() -> None:
            nonlocal starts
            starts += 1

        segmenter.set_on_speech_started(on_speech_started)
        segmenter.accept(np.ones(512 * 2, dtype=np.float32))

        self.assertEqual(starts, 1)


class OpenAICompatibleSpeechToTextClientTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_sends_openai_compatible_multipart_request(self) -> None:
        seen: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            seen["url"] = str(request.url)
            seen["authorization"] = request.headers.get("authorization")
            seen["content_type"] = request.headers.get("content-type")
            seen["body"] = body
            return httpx.Response(200, json={"text": " turn on the light "})

        client = OpenAICompatibleSpeechToTextClient(
            SttSettings(
                enabled=True,
                transcriptions_url="https://stt.example/v1/audio/transcriptions",
                model="whisper-large-turbo",
                api_key="test-key",
                language="en",
            ),
            transport=httpx.MockTransport(handler),
        )

        result = await client.transcribe_wav(encode_wav(np.zeros(512, dtype=np.float32)))

        self.assertEqual(result.text, "turn on the light")
        self.assertEqual(seen["url"], "https://stt.example/v1/audio/transcriptions")
        self.assertEqual(seen["authorization"], "Bearer test-key")
        self.assertIn("multipart/form-data", str(seen["content_type"]))
        body = seen["body"]
        self.assertIsInstance(body, bytes)
        self.assertIn(b'name="model"', body)
        self.assertIn(b"whisper-large-turbo", body)
        self.assertIn(b'name="stream"', body)
        self.assertIn(b"false", body)
        self.assertIn(b'name="language"', body)
        self.assertIn(b"en", body)
        self.assertIn(b'name="file"; filename="utterance.wav"', body)


class TextToSpeechHelpersTestCase(unittest.TestCase):
    def test_semantic_text_chunker_prefers_sentence_boundaries(self) -> None:
        chunker = SemanticTextChunker(min_chars=20, max_chars=80)

        chunks = [
            *chunker.accept("The living room light is now on. "),
            *chunker.accept("I also checked the kitchen sensor"),
        ]
        final = chunker.flush()

        self.assertEqual(chunks, ["The living room light is now on."])
        self.assertEqual(final, "I also checked the kitchen sensor")

    def test_semantic_text_chunker_splits_long_unpunctuated_text(self) -> None:
        chunker = SemanticTextChunker(min_chars=10, max_chars=32)

        chunks = chunker.accept(
            "This response keeps going without punctuation so it should still stream"
        )

        self.assertEqual(chunks, ["This response keeps going", "without punctuation so it"])

    def test_pcm_bytes_to_float32_frames_chunks_audio(self) -> None:
        pcm = np.array([0, 32767, -32768, 16384, -16384], dtype="<i2").tobytes()

        frames = pcm_bytes_to_float32_frames(pcm, frame_samples=2)

        self.assertEqual(len(frames), 3)
        self.assertEqual([frame.shape[0] for frame in frames], [2, 2, 1])
        self.assertAlmostEqual(float(frames[0][0]), 0.0)
        self.assertAlmostEqual(float(frames[0][1]), 32767 / 32768)
        self.assertAlmostEqual(float(frames[1][0]), -1.0)

    def test_pcm_chunker_preserves_split_samples_and_fixed_frames(self) -> None:
        pcm = np.array([0, 32767, -32768, 16384, -16384], dtype="<i2").tobytes()
        chunker = Pcm16FrameChunker(frame_samples=2)

        first_frames = chunker.accept(pcm[:3])
        second_frames = chunker.accept(pcm[3:7])
        final_frames = chunker.accept(pcm[7:])
        flushed_frames = chunker.flush()

        frames = [*first_frames, *second_frames, *final_frames, *flushed_frames]

        self.assertEqual([frame.shape[0] for frame in frames], [2, 2, 2])
        self.assertAlmostEqual(float(frames[0][0]), 0.0)
        self.assertAlmostEqual(float(frames[0][1]), 32767 / 32768)
        self.assertAlmostEqual(float(frames[1][0]), -1.0)
        self.assertAlmostEqual(float(frames[2][0]), -16384 / 32768)
        self.assertAlmostEqual(float(frames[2][1]), 0.0)


class ChunkedByteStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk


class OpenAICompatibleTextToSpeechClientTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_sends_openai_compatible_json_and_streams_pcm(self) -> None:
        seen: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            seen["url"] = str(request.url)
            seen["authorization"] = request.headers.get("authorization")
            seen["accept"] = request.headers.get("accept")
            seen["body"] = json.loads(body)
            return httpx.Response(200, stream=ChunkedByteStream([b"\x00\x01", b"\x02\x03"]))

        client = OpenAICompatibleTextToSpeechClient(
            TtsSettings(
                enabled=True,
                speech_url="http://kokoro.example/v1/audio/speech",
                model="kokoro",
                voice="af_heart",
                api_key="test-key",
                response_format="pcm",
                speed=1.25,
            ),
            transport=httpx.MockTransport(handler),
        )

        chunks = [chunk async for chunk in client.stream_pcm("Hello")]

        self.assertEqual(chunks, [b"\x00\x01", b"\x02\x03"])
        self.assertEqual(seen["url"], "http://kokoro.example/v1/audio/speech")
        self.assertEqual(seen["authorization"], "Bearer test-key")
        self.assertEqual(seen["accept"], "audio/*")
        self.assertEqual(
            seen["body"],
            {
                "input": "Hello",
                "model": "kokoro",
                "voice": "af_heart",
                "response_format": "pcm",
                "speed": 1.25,
            },
        )

    async def test_omits_authorization_header_when_api_key_is_empty(self) -> None:
        seen: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            seen["authorization"] = request.headers.get("authorization")
            return httpx.Response(200, stream=ChunkedByteStream([b"\x00\x01"]))

        client = OpenAICompatibleTextToSpeechClient(
            TtsSettings(
                enabled=True,
                speech_url="http://kokoro.example/v1/audio/speech",
            ),
            transport=httpx.MockTransport(handler),
        )

        chunks = [chunk async for chunk in client.stream_pcm("Hello")]

        self.assertEqual(chunks, [b"\x00\x01"])
        self.assertIsNone(seen["authorization"])

    async def test_http_errors_raise_for_caller_to_record(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, request=request)

        client = OpenAICompatibleTextToSpeechClient(
            TtsSettings(
                enabled=True,
                speech_url="http://kokoro.example/v1/audio/speech",
            ),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(httpx.HTTPStatusError):
            _chunks = [chunk async for chunk in client.stream_pcm("Hello")]


class FakeSegmenter:
    def __init__(self) -> None:
        self.on_speech_started = None

    def set_on_speech_started(self, callback) -> None:
        self.on_speech_started = callback

    def accept(self, _samples):
        return []

    def flush(self):
        return None


class FakeSpeechToTextClient:
    async def transcribe_wav(self, _wav_bytes: bytes) -> TranscriptResult:
        return TranscriptResult(text="turn on the lights")


class SpeechPipelineCancellationTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_interrupt_current_turn_cancels_active_assistant_work(self) -> None:
        submit_started = asyncio.Event()
        submit_cancelled = asyncio.Event()
        release_submit = asyncio.Event()
        submitted_transcripts: list[str] = []
        synthesized: list[str] = []
        assistant_responses: list[str] = []

        async def submit_transcript(_thread_id: str, transcript: str) -> str:
            submit_started.set()
            try:
                await release_submit.wait()
            except asyncio.CancelledError:
                submit_cancelled.set()
                raise
            return f"reply to {transcript}"

        async def synthesize_response(_webrtc_id: str | None, text: str) -> None:
            synthesized.append(text)

        async def run_assistant_work(_webrtc_id, operation):
            return await operation

        pipeline = SpeechPipeline(
            session_id="session-a",
            stt_client=FakeSpeechToTextClient(),
            segmenter=FakeSegmenter(),
            submit_transcript=submit_transcript,
            synthesize_response=synthesize_response,
            on_speech_started=None,
            run_assistant_work=run_assistant_work,
            on_transcript_started=lambda _session_id, _webrtc_id: "transcript-a",
            on_transcript_completed=lambda _transcript_id, _text, _webrtc_id: "thread-a",
            on_transcript_submitted=submitted_transcripts.append,
            on_transcript_failed=lambda _transcript_id, _error: None,
            on_assistant_response=lambda _webrtc_id, text: assistant_responses.append(text),
        )
        pipeline.start()
        await pipeline._utterance_queue.put(
            SpeechUtterance(samples=np.zeros(512, dtype=np.float32))
        )

        await asyncio.wait_for(submit_started.wait(), timeout=1)
        pipeline.interrupt_current_turn()
        await asyncio.wait_for(submit_cancelled.wait(), timeout=1)
        await asyncio.sleep(0)

        self.assertEqual(submitted_transcripts, [])
        self.assertEqual(synthesized, [])
        self.assertEqual(assistant_responses, [])

        await pipeline.close(flush=False)

    async def test_assistant_response_callback_receives_final_text(self) -> None:
        assistant_responses: list[tuple[str | None, str]] = []

        async def submit_transcript(_thread_id: str, transcript: str) -> str:
            return f"reply to {transcript}"

        async def run_assistant_work(_webrtc_id, operation):
            return await operation

        pipeline = SpeechPipeline(
            session_id="session-a",
            stt_client=FakeSpeechToTextClient(),
            segmenter=FakeSegmenter(),
            submit_transcript=submit_transcript,
            synthesize_response=None,
            on_speech_started=None,
            run_assistant_work=run_assistant_work,
            on_transcript_started=lambda _session_id, _webrtc_id: "transcript-a",
            on_transcript_completed=lambda _transcript_id, _text, _webrtc_id: "thread-a",
            on_transcript_submitted=lambda _transcript_id: None,
            on_transcript_failed=lambda _transcript_id, _error: None,
            on_assistant_response=lambda webrtc_id, text: assistant_responses.append(
                (webrtc_id, text)
            ),
        )
        pipeline.set_webrtc_id("webrtc-a")
        await pipeline._transcribe_and_submit(
            SpeechUtterance(samples=np.zeros(512, dtype=np.float32))
        )

        self.assertEqual(
            assistant_responses,
            [("webrtc-a", "reply to turn on the lights")],
        )

    async def test_streamed_response_chunks_are_synthesized_incrementally(self) -> None:
        synthesized: list[tuple[str | None, str]] = []
        assistant_deltas: list[tuple[str | None, str]] = []
        assistant_responses: list[tuple[str | None, str]] = []

        async def submit_transcript(_thread_id: str, _transcript: str) -> str:
            raise AssertionError("streaming path should not call submit_transcript")

        async def stream_transcript(_thread_id: str, _transcript: str):
            yield "First sentence."
            yield "Second sentence."

        async def synthesize_response(webrtc_id: str | None, text: str) -> None:
            synthesized.append((webrtc_id, text))

        pipeline = SpeechPipeline(
            session_id="session-a",
            stt_client=FakeSpeechToTextClient(),
            segmenter=FakeSegmenter(),
            submit_transcript=submit_transcript,
            synthesize_response=synthesize_response,
            on_speech_started=None,
            run_assistant_work=None,
            on_transcript_started=lambda _session_id, _webrtc_id: "transcript-a",
            on_transcript_completed=lambda _transcript_id, _text, _webrtc_id: "thread-a",
            on_transcript_submitted=lambda _transcript_id: None,
            on_transcript_failed=lambda _transcript_id, _error: None,
            on_assistant_response=lambda webrtc_id, text: assistant_responses.append(
                (webrtc_id, text)
            ),
            on_assistant_response_delta=lambda webrtc_id, text: assistant_deltas.append(
                (webrtc_id, text)
            ),
            stream_transcript=stream_transcript,
        )
        pipeline.set_webrtc_id("webrtc-a")

        await pipeline._transcribe_and_submit(
            SpeechUtterance(samples=np.zeros(512, dtype=np.float32))
        )

        self.assertEqual(
            synthesized,
            [("webrtc-a", "First sentence."), ("webrtc-a", "Second sentence.")],
        )
        self.assertEqual(
            assistant_deltas,
            [
                ("webrtc-a", "First sentence."),
                ("webrtc-a", "First sentence. Second sentence."),
            ],
        )
        self.assertEqual(
            assistant_responses,
            [("webrtc-a", "First sentence. Second sentence.")],
        )

    async def test_speech_started_callback_interrupts_current_turn(self) -> None:
        submit_started = asyncio.Event()
        submit_cancelled = asyncio.Event()

        async def submit_transcript(_thread_id: str, _transcript: str) -> str:
            submit_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                submit_cancelled.set()
                raise

        segmenter = FakeSegmenter()
        interrupted_webrtc_ids: list[str | None] = []
        pipeline = SpeechPipeline(
            session_id="session-a",
            stt_client=FakeSpeechToTextClient(),
            segmenter=segmenter,
            submit_transcript=submit_transcript,
            synthesize_response=None,
            on_speech_started=interrupted_webrtc_ids.append,
            run_assistant_work=None,
            on_transcript_started=lambda _session_id, _webrtc_id: "transcript-a",
            on_transcript_completed=lambda _transcript_id, _text, _webrtc_id: "thread-a",
            on_transcript_submitted=lambda _transcript_id: None,
            on_transcript_failed=lambda _transcript_id, _error: None,
        )
        pipeline.set_webrtc_id("webrtc-a")
        pipeline.start()
        await pipeline._utterance_queue.put(
            SpeechUtterance(samples=np.zeros(512, dtype=np.float32))
        )

        await asyncio.wait_for(submit_started.wait(), timeout=1)
        assert segmenter.on_speech_started is not None
        segmenter.on_speech_started()
        await asyncio.wait_for(submit_cancelled.wait(), timeout=1)

        self.assertEqual(interrupted_webrtc_ids, ["webrtc-a"])

        await pipeline.close(flush=False)
