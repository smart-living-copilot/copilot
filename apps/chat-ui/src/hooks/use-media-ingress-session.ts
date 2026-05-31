'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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

type MediaRtcConfiguration = RTCConfiguration & {
  iceGatherTimeoutMs?: number;
};

interface MediaSessionSnapshot {
  assistant_response_pending?: boolean | null;
  latest_assistant_text?: string | null;
  latest_transcript_text?: string | null;
}

interface IceGatherResult {
  candidateCount: number;
  durationMs: number;
  state: RTCIceGatheringState;
  timedOut: boolean;
}

const DEFAULT_ICE_GATHER_TIMEOUT_MS = 750;

function createWebrtcId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `media-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function mediaTimestamp() {
  return Math.round(performance.now());
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

function normalizeIceGatherTimeout(value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return DEFAULT_ICE_GATHER_TIMEOUT_MS;
  }
  return Math.max(0, Math.round(value));
}

function waitForIceGatheringComplete(
  peerConnection: RTCPeerConnection,
  timeoutMs: number,
): Promise<IceGatherResult> {
  if (peerConnection.iceGatheringState === 'complete') {
    return Promise.resolve({
      candidateCount: 0,
      durationMs: 0,
      state: peerConnection.iceGatheringState,
      timedOut: false,
    });
  }

  return new Promise<IceGatherResult>((resolve) => {
    const startedAt = mediaTimestamp();
    let candidateCount = 0;
    const timeout = window.setTimeout(() => done(true), timeoutMs);

    function done(timedOut: boolean) {
      window.clearTimeout(timeout);
      peerConnection.removeEventListener(
        'icegatheringstatechange',
        handleStateChange,
      );
      peerConnection.removeEventListener('icecandidate', handleIceCandidate);
      resolve({
        candidateCount,
        durationMs: mediaTimestamp() - startedAt,
        state: peerConnection.iceGatheringState,
        timedOut,
      });
    }

    function handleIceCandidate(event: RTCPeerConnectionIceEvent) {
      if (event.candidate) {
        candidateCount += 1;
      }
    }

    function handleStateChange() {
      if (peerConnection.iceGatheringState === 'complete') {
        done(false);
      }
    }

    peerConnection.addEventListener('icecandidate', handleIceCandidate);
    peerConnection.addEventListener(
      'icegatheringstatechange',
      handleStateChange,
    );
  });
}

export function useMediaIngressSession(chatId: string): MediaIngressSession {
  const [state, setState] = useState<MediaIngressState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [webrtcId, setWebrtcId] = useState<string | null>(null);
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
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const webrtcIdRef = useRef<string | null>(null);

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

  const cleanupMedia = useCallback((deleteSession: boolean) => {
    const peerConnection = peerConnectionRef.current;
    peerConnectionRef.current = null;
    if (peerConnection) {
      peerConnection.close();
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

    const currentWebrtcId = webrtcIdRef.current;
    webrtcIdRef.current = null;
    setWebrtcId(null);
    if (deleteSession && currentWebrtcId) {
      void fetch(`/api/media/sessions/${encodeURIComponent(currentWebrtcId)}`, {
        method: 'DELETE',
        keepalive: true,
      }).catch(() => {
        // Media cleanup is best-effort; WebRTC close also notifies the backend.
      });
    }
  }, []);

  const stop = useCallback(() => {
    cleanupMedia(true);
    setError(null);
    setState('idle');
  }, [cleanupMedia]);

  const fail = useCallback(
    (message: string) => {
      cleanupMedia(true);
      setError(message);
      setState('error');
    },
    [cleanupMedia],
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
      logMediaConnectionStep(startedAt, 'local media captured', {
        audioTracks: capturedStream.getAudioTracks().length,
        videoTracks: capturedStream.getVideoTracks().length,
      });
      capturedStream.getAudioTracks().forEach((track) => {
        track.enabled = true;
      });
      capturedStream.getVideoTracks().forEach((track) => {
        track.enabled = true;
      });
      streamRef.current = capturedStream;
      setLocalStream(capturedStream);

      setState('connecting');
      const rtcConfigurationResponse = await fetch(
        '/api/media/rtc-configuration',
      );
      if (!rtcConfigurationResponse.ok) {
        throw new Error('Could not load media connection settings');
      }
      const rtcConfigurationResponseBody =
        (await rtcConfigurationResponse.json()) as MediaRtcConfiguration;
      const { iceGatherTimeoutMs: rawIceGatherTimeoutMs, ...rtcConfiguration } =
        rtcConfigurationResponseBody;
      const iceGatherTimeoutMs = normalizeIceGatherTimeout(
        rawIceGatherTimeoutMs,
      );
      logMediaConnectionStep(startedAt, 'rtc configuration loaded', {
        iceGatherTimeoutMs,
        iceServers: rtcConfiguration.iceServers?.length ?? 0,
      });
      const peerConnection = new RTCPeerConnection(rtcConfiguration);
      peerConnectionRef.current = peerConnection;
      peerConnection.createDataChannel('events');

      peerConnection.addEventListener('connectionstatechange', () => {
        if (peerConnectionRef.current !== peerConnection) {
          return;
        }

        if (peerConnection.connectionState === 'connected') {
          logMediaConnectionStep(startedAt, 'peer connection connected', {
            iceConnectionState: peerConnection.iceConnectionState,
            iceGatheringState: peerConnection.iceGatheringState,
          });
          setState('connected');
        }
        if (peerConnection.connectionState === 'failed') {
          fail('Media connection failed');
        }
        if (
          peerConnection.connectionState === 'disconnected' ||
          peerConnection.connectionState === 'closed'
        ) {
          fail('Media connection ended');
        }
      });

      peerConnection.addEventListener('track', (event) => {
        if (peerConnectionRef.current !== peerConnection) {
          return;
        }

        const [stream] = event.streams;
        if (stream) {
          setRemoteStream(stream);
          return;
        }

        setRemoteStream((currentStream) => {
          const nextStream = currentStream ?? new MediaStream();
          if (
            !nextStream.getTracks().some((track) => track.id === event.track.id)
          ) {
            nextStream.addTrack(event.track);
          }
          return nextStream;
        });
      });

      capturedStream.getTracks().forEach((track) => {
        peerConnection.addTrack(track, capturedStream);
      });

      const offer = await peerConnection.createOffer();
      await peerConnection.setLocalDescription(offer);
      logMediaConnectionStep(startedAt, 'local offer created');
      const iceGatherResult = await waitForIceGatheringComplete(
        peerConnection,
        iceGatherTimeoutMs,
      );
      logMediaConnectionStep(startedAt, 'ice gathering wait finished', {
        ...iceGatherResult,
      });

      const nextWebrtcId = createWebrtcId();
      webrtcIdRef.current = nextWebrtcId;
      setWebrtcId(nextWebrtcId);

      const response = await fetch('/api/media/webrtc/offer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sdp: peerConnection.localDescription?.sdp,
          type: peerConnection.localDescription?.type,
          webrtc_id: nextWebrtcId,
        }),
      });
      logMediaConnectionStep(startedAt, 'offer posted', {
        status: response.status,
      });
      const answer = (await response.json()) as
        | RTCSessionDescriptionInit
        | { status: 'failed'; meta?: { error?: string } };

      if (!response.ok || 'status' in answer) {
        throw new Error(
          'meta' in answer && answer.meta?.error
            ? answer.meta.error
            : 'Media connection failed',
        );
      }

      await peerConnection.setRemoteDescription(answer);
      logMediaConnectionStep(startedAt, 'remote answer applied');
      const metadataResponse = await fetch(
        `/api/media/sessions/${encodeURIComponent(nextWebrtcId)}/metadata`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ threadId: chatId }),
        },
      );
      logMediaConnectionStep(startedAt, 'metadata attached', {
        status: metadataResponse.status,
      });
      if (!metadataResponse.ok) {
        throw new Error('Could not attach media session to this chat');
      }
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
  }, [chatId, fail, state]);

  useEffect(() => {
    if (!webrtcId || state !== 'connected') {
      return;
    }

    const eventSource = new EventSource(
      `/api/media/sessions/${encodeURIComponent(webrtcId)}/stream`,
    );

    const handleSnapshot = (event: MessageEvent) => {
      try {
        const snapshot = JSON.parse(event.data) as MediaSessionSnapshot;
        setLatestAssistantText(snapshot.latest_assistant_text?.trim() || null);
        setLatestUserTranscript(
          snapshot.latest_transcript_text?.trim() || null,
        );
        setAssistantResponsePending(
          Boolean(snapshot.assistant_response_pending),
        );
      } catch (parseError) {
        console.debug('Could not parse media snapshot', parseError);
      }
    };

    const handleEnd = () => {
      eventSource.close();
    };

    eventSource.addEventListener('snapshot', handleSnapshot);
    eventSource.addEventListener('end', handleEnd);

    return () => {
      eventSource.removeEventListener('snapshot', handleSnapshot);
      eventSource.removeEventListener('end', handleEnd);
      eventSource.close();
    };
  }, [state, webrtcId]);

  useEffect(() => () => cleanupMedia(true), [cleanupMedia]);

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
