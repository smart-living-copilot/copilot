'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { type Room } from 'livekit-client';

import { requestLiveKitToken } from '@/hooks/media-ingress/livekit-api';
import { startLiveKitConnection } from '@/hooks/media-ingress/livekit-connection';
import { logMediaConnectionStep } from '@/hooks/media-ingress/livekit-utils';
import {
  type MediaIngressSession,
  type MediaIngressState,
} from '@/hooks/media-ingress/types';

export type { MediaIngressSession, MediaIngressState };

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
  const [cameraSnapshotCueSeq, setCameraSnapshotCueSeq] = useState(0);
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
    setCameraSnapshotCueSeq(0);
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
    setCameraSnapshotCueSeq(0);
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
      await startLiveKitConnection({
        chatId,
        connection: liveKitConnection,
        fail,
        liveKitRemoteStreamRef,
        liveKitRoomRef,
        setAssistantResponsePending,
        setLatestAssistantText,
        setLatestUserTranscript,
        setLocalStream,
        setRemoteStream,
        setState,
        onCameraSnapshotSent: () => {
          setCameraSnapshotCueSeq((value) => value + 1);
        },
        startedAt,
        streamRef,
      });
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

  useEffect(() => () => cleanupMedia(), [cleanupMedia]);

  return useMemo(
    () => ({
      state,
      localStream,
      remoteStream,
      error,
      latestAssistantText,
      latestUserTranscript,
      cameraSnapshotCueSeq,
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
      cameraSnapshotCueSeq,
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
