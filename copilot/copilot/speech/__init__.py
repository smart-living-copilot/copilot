"""Speech segmentation, transcription, and synthesis helpers."""

from copilot.speech.audio import (
    TARGET_SAMPLE_RATE,
    TTS_FRAME_SAMPLES,
    TTS_OUTPUT_SAMPLE_RATE,
    VAD_WINDOW_SAMPLES,
    Pcm16FrameChunker,
    encode_wav,
    normalize_audio_frame,
    pcm_bytes_to_float32_frames,
)
from copilot.speech.clients import (
    OpenAICompatibleSpeechToTextClient,
    OpenAICompatibleTextToSpeechClient,
)
from copilot.speech.chunking import SemanticTextChunker
from copilot.speech.manager import SpeechMediaSessionRegistry, SpeechPipelineManager
from copilot.speech.pipeline import (
    AssistantResponse,
    AssistantResponseDelta,
    AssistantWorkRunner,
    SpeechPipeline,
    SpeechStarted,
    SpeechSynthesizer,
    TranscriptCompleted,
    TranscriptFailed,
    TranscriptStarted,
    TranscriptStreamer,
    TranscriptSubmitted,
    TranscriptSubmitter,
    new_transcript_id,
)
from copilot.speech.settings import (
    SttSettings,
    TtsSettings,
    VadSettings,
    settings_from_app_settings,
)
from copilot.speech.types import SpeechUtterance, TranscriptResult
from copilot.speech.vad import (
    SileroSpeechProbabilityDetector,
    SpeechProbabilityDetector,
    VadUtteranceSegmenter,
)

__all__ = [
    "AssistantResponse",
    "AssistantResponseDelta",
    "AssistantWorkRunner",
    "OpenAICompatibleSpeechToTextClient",
    "OpenAICompatibleTextToSpeechClient",
    "Pcm16FrameChunker",
    "SemanticTextChunker",
    "SileroSpeechProbabilityDetector",
    "SpeechPipeline",
    "SpeechMediaSessionRegistry",
    "SpeechPipelineManager",
    "SpeechProbabilityDetector",
    "SpeechStarted",
    "SpeechSynthesizer",
    "SpeechUtterance",
    "SttSettings",
    "TARGET_SAMPLE_RATE",
    "TTS_FRAME_SAMPLES",
    "TTS_OUTPUT_SAMPLE_RATE",
    "TranscriptCompleted",
    "TranscriptFailed",
    "TranscriptResult",
    "TranscriptStarted",
    "TranscriptStreamer",
    "TranscriptSubmitted",
    "TranscriptSubmitter",
    "TtsSettings",
    "VAD_WINDOW_SAMPLES",
    "VadSettings",
    "VadUtteranceSegmenter",
    "encode_wav",
    "new_transcript_id",
    "normalize_audio_frame",
    "pcm_bytes_to_float32_frames",
    "settings_from_app_settings",
]
