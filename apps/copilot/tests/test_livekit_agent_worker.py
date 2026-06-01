import pickle
import asyncio

from copilot.core.settings import Settings
from copilot.workers import livekit
from copilot.workers.livekit import speech as livekit_speech
from copilot.workers.livekit.graph import VoiceSafeGraphStream
from langchain_core.messages import AIMessageChunk


def test_livekit_session_handler_is_spawn_pickleable() -> None:
    assert pickle.loads(pickle.dumps(livekit.smart_living_copilot)) is (
        livekit.smart_living_copilot
    )


def test_livekit_stt_kwargs_use_transcriptions_endpoint_without_llm_key() -> None:
    settings = Settings(
        openai_api_key="llm-key",
        stt_transcriptions_url="http://stt:8000/v1/audio/transcriptions",
        stt_api_key="",
        stt_language="",
    )

    kwargs = livekit_speech.stt_kwargs(settings)

    assert kwargs["base_url"] == "http://stt:8000/v1"
    assert "api_key" not in kwargs
    assert kwargs["detect_language"] is True
    assert "language" not in kwargs


def test_livekit_stt_kwargs_use_dedicated_speech_key_and_language() -> None:
    settings = Settings(
        openai_api_key="llm-key",
        stt_transcriptions_url="http://stt:8000/v1/audio/transcriptions",
        stt_api_key="speech-key",
        stt_language="de",
    )

    kwargs = livekit_speech.stt_kwargs(settings)

    assert kwargs["api_key"] == "speech-key"
    assert kwargs["language"] == "de"
    assert "detect_language" not in kwargs


def test_livekit_tts_kwargs_use_speech_endpoint_without_llm_key() -> None:
    settings = Settings(
        openai_api_key="llm-key",
        tts_speech_url="http://kokoro:8880/v1/audio/speech",
        tts_api_key="",
    )

    kwargs = livekit_speech.tts_kwargs(settings)

    assert kwargs["base_url"] == "http://kokoro:8880/v1"
    assert "api_key" not in kwargs


def test_livekit_tts_kwargs_can_fall_back_to_openai_when_no_speech_url() -> None:
    settings = Settings(
        openai_api_key="llm-key",
        tts_speech_url="",
        tts_api_key="",
    )
    settings.openai_base_url = "http://openai-compatible:8080/v1"

    kwargs = livekit_speech.tts_kwargs(settings)

    assert kwargs["base_url"] == "http://openai-compatible:8080/v1"
    assert kwargs["api_key"] == "llm-key"


def test_livekit_voice_graph_filters_tool_and_router_output_chunks() -> None:
    class FakeGraph:
        def astream(self, *_args, **_kwargs):
            async def events():
                yield (
                    AIMessageChunk(content='{"intent":"control"}'),
                    {"langgraph_node": "router"},
                )
                yield (
                    AIMessageChunk(
                        content="",
                        tool_call_chunks=[
                            {
                                "name": "get_current_time",
                                "args": "{}",
                                "id": "call-1",
                                "index": 0,
                            }
                        ],
                    ),
                    {"langgraph_node": "respond"},
                )
                yield (
                    AIMessageChunk(content='{"raw":"tool result"}'),
                    {"langgraph_node": "respond_tools"},
                )
                yield (
                    AIMessageChunk(content="The light is on."),
                    {"langgraph_node": "respond"},
                )

            return events()

    async def collect_events():
        return [
            event
            async for event in VoiceSafeGraphStream(FakeGraph()).astream(
                {"messages": []},
                {"configurable": {"thread_id": "thread-a"}},
                stream_mode="messages",
            )
        ]

    events = asyncio.run(collect_events())

    assert len(events) == 1
    message, metadata = events[0]
    assert message.content == "The light is on."
    assert metadata == {"langgraph_node": "respond"}
