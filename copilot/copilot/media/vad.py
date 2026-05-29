"""Voice activity detection and utterance segmentation."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from typing import Any, Protocol

from copilot.media.audio import TARGET_SAMPLE_RATE, VAD_WINDOW_SAMPLES
from copilot.media.settings import VadSettings
from copilot.media.types import SpeechUtterance


class SpeechProbabilityDetector(Protocol):
    def reset(self) -> None: ...

    def speech_probability(self, samples: Any) -> float: ...


class SileroSpeechProbabilityDetector:
    """Lazy Silero VAD adapter.

    The import happens only when STT is enabled so unit tests and non-voice
    deployments can run without loading the model.
    """

    _shared_model: Any = None
    _shared_lock = asyncio.Lock()

    def __init__(self) -> None:
        self._model: Any = None

    async def load(self) -> None:
        async with self._shared_lock:
            if SileroSpeechProbabilityDetector._shared_model is None:
                SileroSpeechProbabilityDetector._shared_model = await asyncio.to_thread(
                    self._load_model
                )
            self._model = SileroSpeechProbabilityDetector._shared_model
            self.reset()

    def reset(self) -> None:
        if self._model is not None and hasattr(self._model, "reset_states"):
            self._model.reset_states()

    def speech_probability(self, samples: Any) -> float:
        import numpy as np
        import torch

        if self._model is None:
            raise RuntimeError("Silero VAD model is not loaded")
        tensor = torch.from_numpy(np.asarray(samples, dtype=np.float32))
        with torch.no_grad():
            result = self._model(tensor, TARGET_SAMPLE_RATE)
        if hasattr(result, "item"):
            return float(result.item())
        return float(result)

    @staticmethod
    def _load_model() -> Any:
        from silero_vad import load_silero_vad  # type: ignore[import-untyped]

        try:
            return load_silero_vad(onnx=True)
        except TypeError:
            return load_silero_vad()


class VadUtteranceSegmenter:
    def __init__(self, settings: VadSettings, detector: SpeechProbabilityDetector) -> None:
        import numpy as np

        self._np = np
        self._settings = settings
        self._detector = detector
        self._on_speech_started: Callable[[], None] | None = None
        self._pending = np.array([], dtype=np.float32)
        pad_windows = self._samples_from_ms(settings.speech_pad_ms) // VAD_WINDOW_SAMPLES
        self._pre_speech: deque[Any] = deque(maxlen=max(1, pad_windows))
        self._candidate_chunks: list[Any] = []
        self._utterance_chunks: list[Any] = []
        self._in_speech = False
        self._candidate_speech_samples = 0
        self._speech_samples = 0
        self._silence_samples = 0
        self._total_utterance_samples = 0

    def set_on_speech_started(self, callback: Callable[[], None] | None) -> None:
        self._on_speech_started = callback

    def accept(self, samples: Any) -> list[SpeechUtterance]:
        samples = self._np.asarray(samples, dtype=self._np.float32)
        if samples.size == 0:
            return []
        self._pending = self._np.concatenate([self._pending, samples])

        utterances: list[SpeechUtterance] = []
        while self._pending.size >= VAD_WINDOW_SAMPLES:
            window = self._pending[:VAD_WINDOW_SAMPLES]
            self._pending = self._pending[VAD_WINDOW_SAMPLES:]
            utterance = self._accept_window(window)
            if utterance is not None:
                utterances.append(utterance)
        return utterances

    def flush(self) -> SpeechUtterance | None:
        if self._pending.size:
            padded = self._np.zeros(VAD_WINDOW_SAMPLES, dtype=self._np.float32)
            padded[: self._pending.size] = self._pending
            self._pending = self._np.array([], dtype=self._np.float32)
            utterance = self._accept_window(padded)
            if utterance is not None:
                return utterance
        if self._in_speech and self._speech_samples >= self._samples_from_ms(
            self._settings.min_speech_ms
        ):
            return self._finalize_utterance(trim_trailing_silence=True)
        self.reset()
        return None

    def reset(self) -> None:
        self._pending = self._np.array([], dtype=self._np.float32)
        self._pre_speech.clear()
        self._candidate_chunks = []
        self._utterance_chunks = []
        self._in_speech = False
        self._candidate_speech_samples = 0
        self._speech_samples = 0
        self._silence_samples = 0
        self._total_utterance_samples = 0
        self._detector.reset()

    def _accept_window(self, window: Any) -> SpeechUtterance | None:
        probability = self._detector.speech_probability(window)
        is_speech = probability >= self._settings.threshold

        if not self._in_speech:
            return self._accept_prespeech_window(window, is_speech)
        return self._accept_active_window(window, is_speech)

    def _accept_prespeech_window(self, window: Any, is_speech: bool) -> SpeechUtterance | None:
        if not is_speech:
            self._candidate_chunks = []
            self._candidate_speech_samples = 0
            self._pre_speech.append(window)
            return None

        self._candidate_chunks.append(window)
        self._candidate_speech_samples += window.size
        if self._candidate_speech_samples < self._samples_from_ms(self._settings.min_speech_ms):
            return None

        self._in_speech = True
        self._utterance_chunks = [*self._pre_speech, *self._candidate_chunks]
        self._speech_samples = self._candidate_speech_samples
        self._total_utterance_samples = sum(chunk.size for chunk in self._utterance_chunks)
        self._silence_samples = 0
        self._pre_speech.clear()
        self._candidate_chunks = []
        self._candidate_speech_samples = 0
        if self._on_speech_started is not None:
            self._on_speech_started()
        return self._maybe_force_finalize()

    def _accept_active_window(self, window: Any, is_speech: bool) -> SpeechUtterance | None:
        self._utterance_chunks.append(window)
        self._total_utterance_samples += window.size
        if is_speech:
            self._speech_samples += window.size
            self._silence_samples = 0
        else:
            self._silence_samples += window.size

        forced = self._maybe_force_finalize()
        if forced is not None:
            return forced

        if self._silence_samples >= self._samples_from_ms(self._settings.min_silence_ms):
            return self._finalize_utterance(trim_trailing_silence=True)
        return None

    def _maybe_force_finalize(self) -> SpeechUtterance | None:
        if self._total_utterance_samples >= self._samples_from_ms(self._settings.max_utterance_ms):
            return self._finalize_utterance(trim_trailing_silence=False)
        return None

    def _finalize_utterance(self, *, trim_trailing_silence: bool) -> SpeechUtterance | None:
        audio = self._np.concatenate(self._utterance_chunks) if self._utterance_chunks else None
        silence_samples = self._silence_samples
        self.reset()
        if audio is None or audio.size < self._samples_from_ms(self._settings.min_speech_ms):
            return None

        if trim_trailing_silence:
            keep_silence = self._samples_from_ms(self._settings.speech_pad_ms)
            trim = max(0, silence_samples - keep_silence)
            if trim > 0 and trim < audio.size:
                audio = audio[:-trim]

        return SpeechUtterance(samples=audio, sample_rate=TARGET_SAMPLE_RATE)

    @staticmethod
    def _samples_from_ms(milliseconds: int) -> int:
        return round(TARGET_SAMPLE_RATE * max(0, milliseconds) / 1000)
