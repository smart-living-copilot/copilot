'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Room, RoomEvent, Track } from 'livekit-client';

export type MediaIngressState =
  | 'idle'
  | 'requesting'
  | 'connecting'
  | 'connected'
  | 'error';

export interface MediaIngressSession {
  state: MediaIngressState;
  localStream: MediaStream | null;
  remoteStream: MediaStream | null;
  error: string | null;
  latestAssistantText: string | null;
  latestUserTranscript: string | null;
  isAssistantResponsePending: boolean;
  isMicrophoneMuted: boolean;
  isCameraEnabled: boolean;
  setMicrophoneMuted: (muted: boolean) => void;
  setCameraEnabled: (enabled: boolean) => void;
  start: () => Promise<void>;
  stop: () => void;
}

interface LiveKitTokenResponse {
  enabled?: boolean;
  url?: string;
  token?: string;
  room?: string;
  participantIdentity?: string;
  agentName?: string;
}

interface LiveKitTextStreamReader {
  readAll: () => Promise<string>;
  info?: {
    attributes?: Record<string, string | undefined>;
  };
}

interface LiveKitParticipantInfo {
  identity?: string;
  kind?: string | number;
  name?: string;
}

function logMediaConnectionStep(
  startedAt: number,
  step: string,
  details?: Record<string, unknown>,
) {
  const elapsedMs = Math.round(performance.now() - startedAt);
  console.info('[media] live connection', {
    step,
    elapsedMs,
    ...details,
  });
}

function cloneMediaStream(stream: MediaStream) {
  return new MediaStream(stream.getTracks());
}

function liveKitParticipantLooksLikeAgent(
  participantInfo: LiveKitParticipantInfo,
) {
  const identity = participantInfo.identity?.toLowerCase() || '';
  const kind = String(participantInfo.kind ?? '').toLowerCase();
  return (
    kind.includes('agent') ||
    identity.startsWith('agent-') ||
    identity.includes('copilot')
  );
}

function liveKitSourceForTrack(track: MediaStreamTrack) {
  if (track.kind === 'audio') {
    return Track.Source.Microphone;
  }
  if (track.kind === 'video') {
    return Track.Source.Camera;
  }
  return Track.Source.Unknown;
}

async function requestLiveKitToken(
  chatId: string,
): Promise<LiveKitTokenResponse> {
  const response = await fetch('/api/media/livekit/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ threadId: chatId }),
  });

  const body = (await response.json().catch(() => null)) as
    | (LiveKitTokenResponse & { detail?: string })
    | null;

  if (!response.ok) {
    throw new Error(
      body?.detail || 'Could not load LiveKit connection settings',
    );
  }

  if (!body?.enabled) {
    throw new Error('LiveKit is not configured');
  }

  if (!body.url || !body.token) {
    throw new Error('LiveKit connection settings are incomplete');
  }

  return body;
}

async function requestLiveKitAgentDispatch(
  connection: LiveKitTokenResponse,
  chatId: string,
) {
  if (!connection.room) {
    throw new Error('LiveKit room is missing');
  }

  const response = await fetch('/api/media/livekit/dispatch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      room: connection.room,
      threadId: chatId,
      participantIdentity: connection.participantIdentity || '',
    }),
  });

  const body = (await response.json().catch(() => null)) as
    | { enabled?: boolean; dispatched?: boolean; detail?: string }
    | null;

  if (!response.ok) {
    throw new Error(body?.detail || 'Could not start the LiveKit agent');
  }

  if (!body?.enabled || !body.dispatched) {
    throw new Error('LiveKit agent dispatch is not available');
  }
}

export function useMediaIngressSession(chatId: string): MediaIngressSession {
  const [state, setState] = useState<MediaIngressState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [latestAssistantText, setLatestAssistantText] = useState<string | null>(
    null,
  );
  const [latestUserTranscript, setLatestUserTranscript] = useState<
    string | null
  >(null);
  const [isAssistantResponsePending, setAssistantResponsePending] =
    useState(false);
  const [isMicrophoneMuted, setMicrophoneMutedState] = useState(false);
  const [isCameraEnabled, setCameraEnabledState] = useState(true);
  const liveKitRoomRef = useRef<Room | null>(null);
  const liveKitRemoteStreamRef = useRef<MediaStream | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const setMicrophoneMuted = useCallback((muted: boolean) => {
    setMicrophoneMutedState(muted);
    streamRef.current?.getAudioTracks().forEach((track) => {
      track.enabled = !muted;
    });
  }, []);

  const setCameraEnabled = useCallback((enabled: boolean) => {
    setCameraEnabledState(enabled);
    streamRef.current?.getVideoTracks().forEach((track) => {
      track.enabled = enabled;
    });
  }, []);

  const cleanupMedia = useCallback(() => {
    const liveKitRoom = liveKitRoomRef.current;
    liveKitRoomRef.current = null;
    liveKitRemoteStreamRef.current = null;
    if (liveKitRoom) {
      liveKitRoom.removeAllListeners();
      void liveKitRoom.disconnect();
    }

    const stream = streamRef.current;
    streamRef.current = null;
    stream?.getTracks().forEach((track) => track.stop());
    setLocalStream(null);
    setRemoteStream(null);
    setLatestAssistantText(null);
    setLatestUserTranscript(null);
    setAssistantResponsePending(false);
    setMicrophoneMutedState(false);
    setCameraEnabledState(true);
  }, []);

  const stop = useCallback(() => {
    cleanupMedia();
    setError(null);
    setState('idle');
  }, [cleanupMedia]);

  const fail = useCallback(
    (message: string) => {
      cleanupMedia();
      setError(message);
      setState('error');
    },
    [cleanupMedia],
  );

  const startLiveKitConnection = useCallback(
    async (connection: LiveKitTokenResponse, startedAt: number) => {
      if (!connection.url || !connection.token) {
        throw new Error('LiveKit connection settings are incomplete');
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('Media capture is not available in this browser');
      }

      const capturedStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: {
          width: { ideal: 640 },
          height: { ideal: 360 },
          frameRate: { ideal: 15, max: 30 },
        },
      });
      capturedStream.getAudioTracks().forEach((track) => {
        track.enabled = true;
      });
      capturedStream.getVideoTracks().forEach((track) => {
        track.enabled = true;
      });
      streamRef.current = capturedStream;
      setLocalStream(capturedStream);

      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });
      const nextRemoteStream = new MediaStream();
      liveKitRoomRef.current = room;
      liveKitRemoteStreamRef.current = nextRemoteStream;
      setState('connecting');

      const updateRemoteStream = () => {
        const currentStream = liveKitRemoteStreamRef.current;
        setRemoteStream(currentStream ? cloneMediaStream(currentStream) : null);
      };

      room.on(RoomEvent.Disconnected, () => {
        if (liveKitRoomRef.current === room) {
          fail('Media connection ended');
        }
      });

      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (
          track.kind !== Track.Kind.Audio &&
          track.kind !== Track.Kind.Video
        ) {
          return;
        }
        const mediaTrack = track.mediaStreamTrack;
        if (
          nextRemoteStream
            .getTracks()
            .some((existingTrack) => existingTrack.id === mediaTrack.id)
        ) {
          return;
        }
        nextRemoteStream.addTrack(mediaTrack);
        updateRemoteStream();
      });

      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        if (
          track.kind !== Track.Kind.Audio &&
          track.kind !== Track.Kind.Video
        ) {
          return;
        }
        nextRemoteStream.removeTrack(track.mediaStreamTrack);
        updateRemoteStream();
      });

      room.registerTextStreamHandler(
        'lk.transcription',
        (reader, participantInfo) => {
          void (async () => {
            const message = (
              await (reader as LiveKitTextStreamReader).readAll()
            ).trim();
            if (!message) {
              return;
            }

            const typedParticipant = participantInfo as LiveKitParticipantInfo;
            if (liveKitParticipantLooksLikeAgent(typedParticipant)) {
              setLatestAssistantText(message);
              setAssistantResponsePending(false);
              return;
            }

            setLatestUserTranscript(message);
            if (
              (reader as LiveKitTextStreamReader).info?.attributes?.[
                'lk.transcription_final'
              ] === 'true'
            ) {
              // Clear the previous answer so the pending indicator (thinking
              // dots + waiting sound) shows again for this new turn, not just
              // the first one.
              setLatestAssistantText(null);
              setAssistantResponsePending(true);
            }
          })().catch((transcriptionError) => {
            console.debug(
              'Could not read LiveKit transcription',
              transcriptionError,
            );
          });
        },
      );

      await room.connect(connection.url, connection.token);
      logMediaConnectionStep(startedAt, 'livekit room connected', {
        room: room.name,
      });

      await requestLiveKitAgentDispatch(connection, chatId);
      logMediaConnectionStep(startedAt, 'livekit agent dispatched', {
        room: room.name,
        agentName: connection.agentName,
      });

      for (const track of capturedStream.getTracks()) {
        await room.localParticipant.publishTrack(track, {
          source: liveKitSourceForTrack(track),
        });
      }
      logMediaConnectionStep(startedAt, 'livekit local tracks published', {
        audioTracks: capturedStream.getAudioTracks().length,
        videoTracks: capturedStream.getVideoTracks().length,
      });
      void room.startAudio().catch(() => {
        // Browser autoplay policy may require the existing audio element path.
      });
      setState('connected');
    },
    [chatId, fail],
  );

  const start = useCallback(async () => {
    if (
      state === 'requesting' ||
      state === 'connecting' ||
      state === 'connected'
    ) {
      return;
    }

    setState('requesting');
    setError(null);
    setLatestAssistantText(null);
    setLatestUserTranscript(null);
    setAssistantResponsePending(false);
    setMicrophoneMutedState(false);
    setCameraEnabledState(true);
    const startedAt = performance.now();
    logMediaConnectionStep(startedAt, 'start');

    try {
      const liveKitConnection = await requestLiveKitToken(chatId);
      logMediaConnectionStep(startedAt, 'livekit token loaded', {
        room: liveKitConnection.room,
        participantIdentity: liveKitConnection.participantIdentity,
        agentName: liveKitConnection.agentName,
      });
      await startLiveKitConnection(liveKitConnection, startedAt);
    } catch (startError) {
      logMediaConnectionStep(startedAt, 'failed', {
        error:
          startError instanceof Error
            ? startError.message
            : 'Could not start media stream',
      });
      fail(
        startError instanceof Error
          ? startError.message
          : 'Could not start media stream',
      );
    }
  }, [chatId, fail, startLiveKitConnection, state]);

  useEffect(() => () => cleanupMedia(), [cleanupMedia]);

  return useMemo(
    () => ({
      state,
      localStream,
      remoteStream,
      error,
      latestAssistantText,
      latestUserTranscript,
      isAssistantResponsePending,
      isMicrophoneMuted,
      isCameraEnabled,
      setMicrophoneMuted,
      setCameraEnabled,
      start,
      stop,
    }),
    [
      error,
      isCameraEnabled,
      isAssistantResponsePending,
      isMicrophoneMuted,
      latestAssistantText,
      latestUserTranscript,
      localStream,
      remoteStream,
      setCameraEnabled,
      setMicrophoneMuted,
      start,
      state,
      stop,
    ],
  );
}
