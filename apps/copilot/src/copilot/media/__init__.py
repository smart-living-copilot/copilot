"""Browser media, speech, and live camera helpers."""

from copilot.media.audio import (
    TARGET_SAMPLE_RATE,
    TTS_FRAME_SAMPLES,
    TTS_OUTPUT_SAMPLE_RATE,
    VAD_WINDOW_SAMPLES,
    Pcm16FrameChunker,
    encode_wav,
    normalize_audio_frame,
    pcm_bytes_to_float32_frames,
)
from copilot.media.clients import (
    OpenAICompatibleSpeechToTextClient,
    OpenAICompatibleTextToSpeechClient,
)
from copilot.media.chunking import SemanticTextChunker
from copilot.media.manager import SpeechMediaSessionRegistry, SpeechPipelineManager
from copilot.media.models import MediaSessionStats, MediaTranscript
from copilot.media.pipeline import (
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
from copilot.media.settings import (
    SttSettings,
    TtsSettings,
    VadSettings,
    settings_from_app_settings,
)
from copilot.media.types import SpeechUtterance, TranscriptResult
from copilot.media.vad import (
    SileroSpeechProbabilityDetector,
    SpeechProbabilityDetector,
    VadUtteranceSegmenter,
)
from copilot.media.ingress import (
    MediaSessionRegistry,
    create_media_stream,
    encode_frame_to_jpeg,
    media_sessions,
    parse_rtc_configuration,
    speech_pipelines,
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
    "MediaSessionRegistry",
    "MediaSessionStats",
    "MediaTranscript",
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
    "create_media_stream",
    "encode_wav",
    "encode_frame_to_jpeg",
    "media_sessions",
    "new_transcript_id",
    "normalize_audio_frame",
    "parse_rtc_configuration",
    "pcm_bytes_to_float32_frames",
    "settings_from_app_settings",
    "speech_pipelines",
]
