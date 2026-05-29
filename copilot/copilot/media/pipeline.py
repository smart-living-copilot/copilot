"""Speech pipeline orchestration."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from copilot.media.audio import encode_wav, normalize_audio_frame
from copilot.media.clients import OpenAICompatibleSpeechToTextClient
from copilot.media.types import SpeechUtterance
from copilot.media.vad import VadUtteranceSegmenter

logger = logging.getLogger(__name__)

type TranscriptSubmitter = Callable[[str, str], Awaitable[str]]
type TranscriptStreamer = Callable[[str, str], AsyncIterator[str]]
type SpeechSynthesizer = Callable[[str | None, str], Awaitable[None]]
type SpeechStarted = Callable[[str | None], None]
type AssistantWorkRunner = Callable[[str | None, Awaitable[str]], Awaitable[str]]
type TranscriptStarted = Callable[[str, str | None], str]
type TranscriptCompleted = Callable[[str, str, str | None], str | None]
type TranscriptSubmitted = Callable[[str], None]
type TranscriptFailed = Callable[[str, str], None]
type AssistantResponse = Callable[[str | None, str], None]
type AssistantResponseDelta = Callable[[str | None, str], None]


class SpeechPipeline:
    def __init__(
        self,
        *,
        session_id: str,
        stt_client: OpenAICompatibleSpeechToTextClient,
        segmenter: VadUtteranceSegmenter,
        submit_transcript: TranscriptSubmitter | None,
        synthesize_response: SpeechSynthesizer | None,
        on_speech_started: SpeechStarted | None,
        run_assistant_work: AssistantWorkRunner | None,
        on_transcript_started: TranscriptStarted,
        on_transcript_completed: TranscriptCompleted,
        on_transcript_submitted: TranscriptSubmitted,
        on_transcript_failed: TranscriptFailed,
        on_assistant_response: AssistantResponse | None = None,
        on_assistant_response_delta: AssistantResponseDelta | None = None,
        stream_transcript: TranscriptStreamer | None = None,
    ) -> None:
        self.session_id = session_id
        self._stt_client = stt_client
        self._segmenter = segmenter
        self._submit_transcript = submit_transcript
        self._synthesize_response = synthesize_response
        self._on_speech_started = on_speech_started
        self._run_assistant_work = run_assistant_work
        self._on_transcript_started = on_transcript_started
        self._on_transcript_completed = on_transcript_completed
        self._on_transcript_submitted = on_transcript_submitted
        self._on_transcript_failed = on_transcript_failed
        self._on_assistant_response = on_assistant_response
        self._on_assistant_response_delta = on_assistant_response_delta
        self._stream_transcript = stream_transcript
        self._audio_queue: asyncio.Queue[tuple[int, Any] | None] = asyncio.Queue(maxsize=32)
        self._utterance_queue: asyncio.Queue[SpeechUtterance | None] = asyncio.Queue(maxsize=8)
        self._audio_task: asyncio.Task[None] | None = None
        self._stt_task: asyncio.Task[None] | None = None
        self._current_turn_task: asyncio.Task[None] | None = None
        self._webrtc_id: str | None = None
        self._closed = False
        self._segmenter.set_on_speech_started(self._handle_speech_started)

    @property
    def webrtc_id(self) -> str | None:
        return self._webrtc_id

    def set_webrtc_id(self, webrtc_id: str | None) -> None:
        if webrtc_id:
            self._webrtc_id = webrtc_id

    def start(self) -> None:
        if self._closed:
            return
        if self._audio_task is None:
            self._audio_task = asyncio.create_task(self._run_audio_loop())
            self._audio_task.add_done_callback(self._log_task_result)
        if self._stt_task is None:
            self._stt_task = asyncio.create_task(self._run_stt_loop())
            self._stt_task.add_done_callback(self._log_task_result)

    def enqueue_audio(self, sample_rate: int, audio: Any) -> None:
        if self._closed:
            return
        try:
            self._audio_queue.put_nowait((sample_rate, audio))
        except asyncio.QueueFull:
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._audio_queue.put_nowait((sample_rate, audio))

    def interrupt_current_turn(self) -> None:
        if self._current_turn_task is not None and not self._current_turn_task.done():
            self._current_turn_task.cancel()

    async def close(self, *, flush: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        if flush:
            utterance = self._segmenter.flush()
            if utterance is not None:
                await self._utterance_queue.put(utterance)
        if self._audio_task is not None:
            self._audio_task.cancel()
        await self._utterance_queue.put(None)
        if self._stt_task is not None:
            try:
                await asyncio.wait_for(self._stt_task, timeout=10)
            except (asyncio.CancelledError, TimeoutError):
                self._stt_task.cancel()

    async def _run_audio_loop(self) -> None:
        while True:
            item = await self._audio_queue.get()
            if item is None:
                return
            sample_rate, audio = item
            normalized = normalize_audio_frame(audio, sample_rate)
            for utterance in self._segmenter.accept(normalized):
                await self._utterance_queue.put(utterance)

    async def _run_stt_loop(self) -> None:
        while True:
            utterance = await self._utterance_queue.get()
            if utterance is None:
                return
            self._current_turn_task = asyncio.create_task(self._transcribe_and_submit(utterance))
            try:
                await self._current_turn_task
            except asyncio.CancelledError:
                if self._closed:
                    raise
                logger.info("Voice turn interrupted for session %s", self.session_id)
            except Exception:
                logger.exception("Unhandled speech pipeline error for session %s", self.session_id)
            finally:
                self._current_turn_task = None

    async def _transcribe_and_submit(self, utterance: SpeechUtterance) -> None:
        transcript_id: str | None = None
        try:
            transcript_id = self._on_transcript_started(self.session_id, self._webrtc_id)
            result = await self._stt_client.transcribe_wav(
                encode_wav(utterance.samples, utterance.sample_rate)
            )
            if not result.text:
                self._on_transcript_failed(transcript_id, "Transcription was empty")
                return
            thread_id = self._on_transcript_completed(transcript_id, result.text, self._webrtc_id)
            if thread_id and (
                self._stream_transcript is not None or self._submit_transcript is not None
            ):
                if self._stream_transcript is not None:
                    assistant_text = await self._stream_and_synthesize_response(
                        thread_id,
                        result.text,
                    )
                else:
                    assert self._submit_transcript is not None
                    assistant_work = self._submit_transcript(thread_id, result.text)
                    if self._run_assistant_work is not None:
                        assistant_text = await self._run_assistant_work(
                            self._webrtc_id,
                            assistant_work,
                        )
                    else:
                        assistant_text = await assistant_work
                    if self._synthesize_response is not None and assistant_text:
                        await self._synthesize_response(self._webrtc_id, assistant_text)
                self._on_transcript_submitted(transcript_id)
                if self._on_assistant_response is not None and assistant_text:
                    self._on_assistant_response(self._webrtc_id, assistant_text)
        except asyncio.CancelledError:
            logger.info("Cancelled active voice turn for media session %s", self.session_id)
            raise
        except Exception as exc:
            logger.exception("Failed to transcribe media session %s", self.session_id)
            if transcript_id is not None:
                self._on_transcript_failed(transcript_id, str(exc))

    async def _stream_and_synthesize_response(self, thread_id: str, transcript: str) -> str:
        if self._stream_transcript is None:
            return ""

        chunks: list[str] = []
        async for chunk in self._stream_transcript(thread_id, transcript):
            chunk = chunk.strip()
            if not chunk:
                continue
            chunks.append(chunk)
            if self._on_assistant_response_delta is not None:
                self._on_assistant_response_delta(self._webrtc_id, " ".join(chunks).strip())
            if self._synthesize_response is not None:
                await self._synthesize_response(self._webrtc_id, chunk)
        return " ".join(chunks).strip()

    def _handle_speech_started(self) -> None:
        self.interrupt_current_turn()
        if self._on_speech_started is not None:
            self._on_speech_started(self._webrtc_id)

    @staticmethod
    def _log_task_result(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Speech pipeline task failed")


def new_transcript_id() -> str:
    return f"transcript-{uuid.uuid4()}"
