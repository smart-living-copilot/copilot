"""Audio conversion helpers for browser speech ingress."""

from __future__ import annotations

import io
import wave
from typing import Any

TARGET_SAMPLE_RATE = 16000
TTS_OUTPUT_SAMPLE_RATE = 24000
TTS_FRAME_SAMPLES = 480
VAD_WINDOW_SAMPLES = 512


def normalize_audio_frame(frame: Any, sample_rate: int) -> Any:
    import numpy as np

    audio = np.asarray(frame)
    if audio.ndim > 1:
        audio = audio.mean(axis=0)
    audio = audio.astype(np.float32, copy=False)

    max_abs = float(np.max(np.abs(audio))) if audio.size else 0.0
    if max_abs > 1.0:
        audio = audio / 32768.0

    if sample_rate == TARGET_SAMPLE_RATE or audio.size == 0:
        return np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)

    target_length = max(1, round(audio.size * TARGET_SAMPLE_RATE / sample_rate))
    old_positions = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
    new_positions = np.linspace(0.0, 1.0, num=target_length, endpoint=False)
    resampled = np.interp(new_positions, old_positions, audio)
    return np.clip(resampled, -1.0, 1.0).astype(np.float32, copy=False)


def encode_wav(samples: Any, sample_rate: int = TARGET_SAMPLE_RATE) -> bytes:
    import numpy as np

    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
    return output.getvalue()


def pcm_bytes_to_float32_frames(
    pcm_bytes: bytes,
    *,
    frame_samples: int = TTS_FRAME_SAMPLES,
) -> list[Any]:
    import numpy as np

    if not pcm_bytes:
        return []
    usable_length = len(pcm_bytes) - (len(pcm_bytes) % 2)
    if usable_length <= 0:
        return []
    samples = np.frombuffer(pcm_bytes[:usable_length], dtype="<i2").astype(np.float32)
    samples = samples / 32768.0
    return [
        samples[index : index + frame_samples].copy()
        for index in range(0, samples.size, frame_samples)
        if samples[index : index + frame_samples].size > 0
    ]


class Pcm16FrameChunker:
    def __init__(self, *, frame_samples: int = TTS_FRAME_SAMPLES) -> None:
        import numpy as np

        self._np = np
        self._frame_samples = frame_samples
        self._pending_bytes = b""
        self._pending_samples = np.array([], dtype=np.float32)

    def accept(self, pcm_bytes: bytes) -> list[Any]:
        if not pcm_bytes:
            return []
        pcm_bytes = self._pending_bytes + pcm_bytes
        usable_length = len(pcm_bytes) - (len(pcm_bytes) % 2)
        self._pending_bytes = pcm_bytes[usable_length:]
        if usable_length <= 0:
            return []

        samples = self._decode_samples(pcm_bytes[:usable_length])
        if self._pending_samples.size:
            samples = self._np.concatenate([self._pending_samples, samples])

        complete_length = (samples.size // self._frame_samples) * self._frame_samples
        if complete_length == 0:
            self._pending_samples = samples
            return []

        complete = samples[:complete_length]
        self._pending_samples = samples[complete_length:]
        return [
            complete[index : index + self._frame_samples].copy()
            for index in range(0, complete.size, self._frame_samples)
        ]

    def flush(self) -> list[Any]:
        if self._pending_bytes:
            self._pending_bytes = b""
        if self._pending_samples.size == 0:
            return []

        frame = self._np.zeros(self._frame_samples, dtype=self._np.float32)
        frame[: self._pending_samples.size] = self._pending_samples[: self._frame_samples]
        self._pending_samples = self._np.array([], dtype=self._np.float32)
        return [frame]

    def _decode_samples(self, pcm_bytes: bytes) -> Any:
        samples = self._np.frombuffer(pcm_bytes, dtype="<i2").astype(self._np.float32)
        return samples / 32768.0
