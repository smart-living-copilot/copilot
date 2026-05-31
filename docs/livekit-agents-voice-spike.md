# LiveKit Agents Voice Spike

## Goal

Replace the custom browser WebRTC, VAD, STT, TTS, and speech pipeline glue with
LiveKit Agents, while keeping the existing LangGraph application as the core
reasoning layer.

This is not a proposal to replace LangGraph. LiveKit should own realtime media
transport and voice-agent session handling. LangGraph should remain the source
of truth for prompts, tools, checkpointed thread state, and smart-home behavior.

## Relevant Sources

- LiveKit Agents overview:
  https://docs.livekit.io/agents/
- LiveKit Voice AI quickstart:
  https://docs.livekit.io/agents/start/voice-ai/
- LiveKit LangChain/LangGraph integration:
  https://docs.livekit.io/agents/models/llm/langchain/
- LiveKit OpenAI Realtime plugin:
  https://docs.livekit.io/agents/models/realtime/plugins/openai/
- LiveKit access tokens and room grants:
  https://docs.livekit.io/frontends/authentication/tokens/
- User-provided LangGraph example:
  https://github.com/livekit/agents/blob/1dcdb942571348ef7bb216de12b8058aa8b3f8f4/examples/voice_agents/langgraph_agent.py#L7

## Key Finding

LiveKit Agents already has an official LangChain/LangGraph adapter. The
`livekit.plugins.langchain.LLMAdapter` accepts a locally compiled LangGraph graph
and lets an `AgentSession` use that graph as its LLM-like brain. This means the
cleanest spike does not need a custom LLM bridge at first.

The important architectural choice is where the graph lives:

1. Compile the graph inside a separate LiveKit agent worker and wrap it with
   `LLMAdapter`.
2. Keep the graph owned by the FastAPI app and let the LiveKit agent call an
   internal graph streaming endpoint.

Option 1 is closer to the LiveKit example and should be the first spike. Option
2 is the fallback if thread locking, checkpoint ownership, or deployment shape
make a separate graph worker too risky.

## OpenAI-Compatible Endpoint Handling

The existing LangGraph path should continue using the configured
OpenAI-compatible LLM endpoint. The current graph creates `ChatOpenAI` with
`OPENAI_MODEL`, `OPENAI_API_KEY`, and `OPENAI_API_BASE_URL`, so wrapping that
compiled graph with LiveKit's `LLMAdapter` does not require moving the LLM call
to LiveKit.

Speech is different. If LiveKit owns STT and TTS, the LiveKit agent session must
be configured with matching endpoint settings:

- LLM through LangGraph: keep using `OPENAI_API_BASE_URL`, `OPENAI_API_KEY`, and
  `OPENAI_MODEL`.
- Vision through LangGraph tools: keep using `VISION_API_BASE_URL` or the
  `OPENAI_API_BASE_URL` fallback.
- Embeddings/search: keep using `OPENAI_EMBEDDING_API_BASE_URL`,
  `OPENAI_EMBEDDING_API_KEY`, and `OPENAI_EMBEDDING_MODEL`.
- STT through LiveKit: map the existing `STT_TRANSCRIPTIONS_URL`, `STT_API_KEY`,
  `STT_MODEL`, and `STT_LANGUAGE` to a LiveKit STT provider or a small custom STT
  adapter.
- TTS through LiveKit: map the existing `TTS_SPEECH_URL`, `TTS_API_KEY`,
  `TTS_MODEL`, `TTS_VOICE`, `TTS_RESPONSE_FORMAT`, and `TTS_SPEED` to a LiveKit
  TTS provider or a small custom TTS adapter.

LiveKit's OpenAI plugin supports OpenAI-compatible LLM endpoints via
`openai.LLM(base_url=..., api_key=...)`, but we should only use that directly if
we decide to let LiveKit call the LLM itself. With `LLMAdapter`, LangGraph keeps
that responsibility. The Python OpenAI STT and TTS plugin APIs also expose
`base_url` and `api_key`, so OpenAI-compatible speech endpoints may be usable
directly if their request and streaming behavior matches LiveKit's expectations.
Kokoro should be verified because the current code calls its `/v1/audio/speech`
endpoint directly and streams PCM chunks.

## Recommended Architecture

Browser:

- Use `livekit-client` or LiveKit React components instead of manual
  `RTCPeerConnection` setup.
- Request a short-lived LiveKit token from the backend.
- Join a LiveKit room and publish microphone audio and, when enabled, camera
  video.

Backend API:

- Add a token endpoint, for example `/media/livekit/token`.
- Generate a LiveKit access token with room join permissions.
- Put the current `thread_id` into participant metadata, participant attributes,
  or room-agent dispatch metadata.
- Keep the existing HTTP chat and thread APIs unchanged.

LiveKit agent worker:

- Join the same LiveKit room as an agent participant.
- Configure LiveKit STT, turn detection, interruption handling, and TTS.
- Use the compiled LangGraph graph through `langchain.LLMAdapter`, or call the
  existing graph streaming endpoint if shared graph ownership is needed.
- Pass the thread identity into LangGraph config so checkpointing remains tied to
  the same conversation.

LangGraph:

- Keep the current graph, prompts, tools, and state model.
- Extract graph construction from `agent_app.py` into a reusable factory if the
  LiveKit worker compiles its own graph.
- Review process-local `_thread_run_locks`; a separate worker cannot rely on
  those locks unless they move to a shared mechanism or the graph remains behind
  one FastAPI-owned endpoint.

## What This Could Remove

Likely replace or retire:

- `apps/copilot/src/copilot/media:create_media_stream`
- FastRTC as the browser media ingress path
- The manual WebRTC offer flow in
  `apps/chat-ui/src/hooks/use-media-ingress-session.ts`
- `/media/rtc-configuration`
- `/media/webrtc/offer`
- Most of the custom speech stack under `apps/copilot/src/copilot/media`, including VAD,
  STT orchestration, TTS queuing, and playback interruption code
- The direct `silero-vad` dependency if LiveKit's own VAD or turn detector is
  used instead

Likely keep or adapt:

- `MediaSessionRegistry`, or a LiveKit-backed equivalent, if the UI still needs
  session snapshots and text status
- `/media/sessions/{id}/stream`, if the current UI should keep receiving
  transcript and assistant text updates over SSE
- The `look_at_camera` behavior, but the image source should become the LiveKit
  video track instead of FastRTC frame capture
- The LangGraph streaming semantics in `_stream_voice_transcript_to_chat`, unless
  `LLMAdapter` gives enough streaming and UI event fidelity directly

## Open Questions

- Does `LLMAdapter` preserve the exact message and stream shape the current UI
  expects, or do we need an event adapter around it?
- Can the current LangGraph checkpointer and thread store safely run in both the
  FastAPI process and a LiveKit agent worker?
- Should `_thread_run_locks` become distributed, or should all voice turns call
  one graph runner endpoint?
- How should `look_at_camera` choose the latest video frame when the source is a
  LiveKit room track?
- Do we want OpenAI Realtime for STT/turn detection with text-only output plus a
  separate TTS plugin, or a more classic STT plus LLMAdapter plus TTS pipeline?
- Does the current Kokoro/OpenAI-compatible TTS endpoint map cleanly to a
  LiveKit TTS plugin, or do we need a small custom TTS adapter?

## Suggested Migration Plan

1. Add optional LiveKit config and dependencies without removing FastRTC.
2. Extract graph construction into a reusable function that both FastAPI and a
   worker can call.
3. Add a minimal LiveKit voice worker that joins one room and uses
   `langchain.LLMAdapter(graph=compiled_graph)`.
4. Add a backend token endpoint with `thread_id` propagation.
5. Add a feature-flagged frontend path using LiveKit client connection instead
   of manual WebRTC offer creation.
6. Verify end-to-end voice turn flow: user speech, transcript, LangGraph tool
   calls, assistant response, TTS, interruption.
7. Verify camera-frame parity for `look_at_camera`.
8. Once parity is good, remove the custom FastRTC/speech stack and simplify the
   media API around LiveKit session state.

## Recommendation

Proceed with a small LiveKit worker spike using `LLMAdapter` first. That is the
lowest-friction way to validate that LiveKit can replace the speech/WebRTC layer
without disturbing the LangGraph core. Treat graph ownership and thread locking
as the main proof point. If that becomes awkward, keep LangGraph behind a single
internal graph streaming endpoint and let LiveKit own only media and voice
session orchestration.
