"""Shared speech data structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from copilot.speech.audio import TARGET_SAMPLE_RATE


@dataclass(frozen=True)
class TranscriptResult:
    text: str


@dataclass(frozen=True)
class SpeechUtterance:
    samples: Any
    sample_rate: int = TARGET_SAMPLE_RATE
