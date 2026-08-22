'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Track, type Room } from 'livekit-client';

import { requestLiveKitToken } from '@/hooks/media-ingress/livekit-api';
import { startLiveKitConnection } from '@/hooks/media-ingress/livekit-connection';
import {
  cloneMediaStream,
  logMediaConnectionStep,
} from '@/hooks/media-ingress/livekit-utils';
import {
  type CameraFacingMode,
  type MediaIngressSession,
  type MediaIngressState,
} from '@/hooks/media-ingress/types';

export type { MediaIngressSession, MediaIngressState };

const LIVE_VIDEO_CONSTRAINTS = {
  width: { ideal: 640 },
  height: { ideal: 360 },
  frameRate: { ideal: 15, max: 30 },
} satisfies MediaTrackConstraints;

function getNextCameraFacingMode(
  facingMode: CameraFacingMode,
): CameraFacingMode {
  return facingMode === 'user' ? 'environment' : 'user';
}

function getTrackFacingMode(
  track: MediaStreamTrack | null | undefined,
  fallback: CameraFacingMode,
): CameraFacingMode {
  const facingMode = track?.getSettings().facingMode;
  return facingMode === 'environment' || facingMode === 'user'
    ? facingMode
    : fallback;
}

function getVideoSwitchConstraints(
  facingMode: CameraFacingMode,
  preference: 'exact' | 'ideal',
): MediaTrackConstraints {
  return {
    ...LIVE_VIDEO_CONSTRAINTS,
    facingMode:
      preference === 'exact' ? { exact: facingMode } : { ideal: facingMode },
  };
}

async function captureCameraTrack(
  facingMode: CameraFacingMode,
): Promise<MediaStreamTrack> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('Media capture is not available in this browser');
  }

  const capture = async (preference: 'exact' | 'ideal') => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: getVideoSwitchConstraints(facingMode, preference),
    });
    const track = stream.getVideoTracks()[0];
    if (!track) {
      stream.getTracks().forEach((streamTrack) => streamTrack.stop());
      throw new Error('No camera track was captured');
    }
    return track;
  };

  try {
    return await capture('exact');
  } catch (error) {
    console.debug('Could not capture exact camera facing mode', error);
    return capture('ideal');
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
  const [cameraSnapshotCueSeq, setCameraSnapshotCueSeq] = useState(0);
  const [isAssistantResponsePending, setAssistantResponsePending] =
    useState(false);
  const [cameraFacingMode, setCameraFacingModeState] =
    useState<CameraFacingMode>('user');
  const [canSwitchCamera, setCanSwitchCamera] = useState(false);
  const [isMicrophoneMuted, setMicrophoneMutedState] = useState(false);
  const [isCameraEnabled, setCameraEnabledState] = useState(false);
  const [isSwitchingCamera, setSwitchingCameraState] = useState(false);
  const cameraFacingModeRef = useRef<CameraFacingMode>('user');
  const isCameraEnabledRef = useRef(false);
  const isSwitchingCameraRef = useRef(false);
  const mediaSessionGenerationRef = useRef(0);
  const pendingCameraTrackRef = useRef<MediaStreamTrack | null>(null);
  const liveKitRoomRef = useRef<Room | null>(null);
  const liveKitRemoteStreamRef = useRef<MediaStream | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const setCameraFacingMode = useCallback((facingMode: CameraFacingMode) => {
    cameraFacingModeRef.current = facingMode;
    setCameraFacingModeState(facingMode);
  }, []);

  const refreshCameraAvailability = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setCanSwitchCamera(false);
      return false;
    }

    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoInputs = devices.filter(
        (device) => device.kind === 'videoinput',
      );
      const distinctIds = new Set(
        videoInputs
          .map((device) => device.deviceId || device.label)
          .filter(Boolean),
      );
      const cameraCount = distinctIds.size || videoInputs.length;
      const nextCanSwitchCamera = cameraCount > 1;
      setCanSwitchCamera(nextCanSwitchCamera);
      return nextCanSwitchCamera;
    } catch (availabilityError) {
      console.debug('Could not enumerate camera devices', availabilityError);
      setCanSwitchCamera(false);
      return false;
    }
  }, []);

  const setMicrophoneMuted = useCallback((muted: boolean) => {
    setMicrophoneMutedState(muted);
    streamRef.current?.getAudioTracks().forEach((track) => {
      track.enabled = !muted;
    });
  }, []);

  const setCameraEnabled = useCallback(
    async (enabled: boolean) => {
      if (
        isSwitchingCameraRef.current ||
        state !== 'connected' ||
        enabled === isCameraEnabledRef.current
      ) {
        return;
      }

      const room = liveKitRoomRef.current;
      const currentStream = streamRef.current;
      if (!room || !currentStream) {
        return;
      }
      const sessionGeneration = mediaSessionGenerationRef.current;
      const isCurrentSession = () =>
        mediaSessionGenerationRef.current === sessionGeneration &&
        liveKitRoomRef.current === room &&
        streamRef.current === currentStream;

      isSwitchingCameraRef.current = true;
      setSwitchingCameraState(true);

      if (!enabled) {
        isCameraEnabledRef.current = false;
        setCameraEnabledState(false);
        try {
          const publication = room.localParticipant.getTrackPublication(
            Track.Source.Camera,
          );
          if (publication?.videoTrack) {
            await room.localParticipant.unpublishTrack(
              publication.videoTrack,
              true,
            );
          }
        } catch (disableError) {
          console.debug('Could not unpublish camera track', disableError);
        } finally {
          const videoTracks = currentStream.getVideoTracks();
          videoTracks.forEach((track) => {
            currentStream.removeTrack(track);
            track.stop();
          });
          if (isCurrentSession()) {
            setLocalStream(cloneMediaStream(currentStream));
            isSwitchingCameraRef.current = false;
            setSwitchingCameraState(false);
          }
        }
        return;
      }

      let videoTrack: MediaStreamTrack | null = null;
      try {
        videoTrack = await captureCameraTrack(cameraFacingModeRef.current);
        if (!isCurrentSession()) {
          videoTrack.stop();
          return;
        }
        pendingCameraTrackRef.current = videoTrack;
        await room.localParticipant.publishTrack(videoTrack, {
          source: Track.Source.Camera,
        });
        if (!isCurrentSession()) {
          try {
            await room.localParticipant.unpublishTrack(videoTrack, true);
          } catch (unpublishError) {
            console.debug(
              'Could not unpublish camera from a closed media session',
              unpublishError,
            );
          } finally {
            videoTrack.stop();
          }
          return;
        }
        if (pendingCameraTrackRef.current === videoTrack) {
          pendingCameraTrackRef.current = null;
        }

        const oldVideoTracks = currentStream.getVideoTracks();
        oldVideoTracks.forEach((track) => currentStream.removeTrack(track));
        currentStream.addTrack(videoTrack);
        setLocalStream(cloneMediaStream(currentStream));
        oldVideoTracks.forEach((track) => {
          if (track.id !== videoTrack?.id) {
            track.stop();
          }
        });

        setCameraFacingMode(
          getTrackFacingMode(videoTrack, cameraFacingModeRef.current),
        );
        isCameraEnabledRef.current = true;
        setCameraEnabledState(true);
        void refreshCameraAvailability();
      } catch (enableError) {
        videoTrack?.stop();
        console.debug('Could not enable camera', enableError);
        if (isCurrentSession()) {
          isCameraEnabledRef.current = false;
          setCameraEnabledState(false);
        }
      } finally {
        if (pendingCameraTrackRef.current === videoTrack) {
          pendingCameraTrackRef.current = null;
        }
        if (isCurrentSession()) {
          isSwitchingCameraRef.current = false;
          setSwitchingCameraState(false);
        }
      }
    },
    [refreshCameraAvailability, setCameraFacingMode, state],
  );

  const switchCamera = useCallback(async () => {
    if (
      isSwitchingCameraRef.current ||
      !isCameraEnabledRef.current ||
      state !== 'connected'
    ) {
      return;
    }

    const room = liveKitRoomRef.current;
    const currentStream = streamRef.current;
    if (!room || !currentStream) {
      return;
    }
    const sessionGeneration = mediaSessionGenerationRef.current;
    const isCurrentSession = () =>
      mediaSessionGenerationRef.current === sessionGeneration &&
      liveKitRoomRef.current === room &&
      streamRef.current === currentStream;

    const hasMultipleCameras =
      canSwitchCamera || (await refreshCameraAvailability());
    if (!isCurrentSession() || !hasMultipleCameras) {
      return;
    }

    const nextFacingMode = getNextCameraFacingMode(cameraFacingModeRef.current);
    let nextVideoTrack: MediaStreamTrack | null = null;
    isSwitchingCameraRef.current = true;
    setSwitchingCameraState(true);

    try {
      const publication = room.localParticipant.getTrackPublication(
        Track.Source.Camera,
      );
      try {
        nextVideoTrack = await captureCameraTrack(nextFacingMode);
        if (!isCurrentSession()) {
          nextVideoTrack.stop();
          return;
        }
        pendingCameraTrackRef.current = nextVideoTrack;
        nextVideoTrack.enabled = isCameraEnabledRef.current;

        if (publication?.videoTrack) {
          await publication.videoTrack.replaceTrack(nextVideoTrack, {
            stopProcessor: true,
            userProvidedTrack: true,
          });
        } else {
          await room.localParticipant.publishTrack(nextVideoTrack, {
            source: Track.Source.Camera,
          });
        }
        if (!isCurrentSession()) {
          nextVideoTrack.stop();
          return;
        }
        if (pendingCameraTrackRef.current === nextVideoTrack) {
          pendingCameraTrackRef.current = null;
        }
      } catch (replaceError) {
        nextVideoTrack?.stop();
        if (pendingCameraTrackRef.current === nextVideoTrack) {
          pendingCameraTrackRef.current = null;
        }
        nextVideoTrack = null;
        if (!isCurrentSession()) {
          return;
        }
        if (!publication?.videoTrack) {
          throw replaceError;
        }

        console.debug(
          'Could not replace camera directly; restarting camera track',
          replaceError,
        );
        await publication.videoTrack.restartTrack({
          facingMode: nextFacingMode,
        });
        if (!isCurrentSession()) {
          publication.videoTrack.stop();
          return;
        }
        nextVideoTrack = publication.videoTrack.mediaStreamTrack;
      }
      nextVideoTrack.enabled = isCameraEnabledRef.current;

      const nextStream = streamRef.current ?? new MediaStream();
      const oldVideoTracks = nextStream.getVideoTracks();
      oldVideoTracks.forEach((track) => nextStream.removeTrack(track));
      nextStream.addTrack(nextVideoTrack);
      streamRef.current = nextStream;
      setLocalStream(cloneMediaStream(nextStream));
      oldVideoTracks.forEach((track) => {
        if (track.id !== nextVideoTrack?.id) {
          track.stop();
        }
      });

      setCameraFacingMode(getTrackFacingMode(nextVideoTrack, nextFacingMode));
      void refreshCameraAvailability();
    } catch (switchError) {
      nextVideoTrack?.stop();
      console.debug('Could not switch camera', switchError);
    } finally {
      if (pendingCameraTrackRef.current === nextVideoTrack) {
        pendingCameraTrackRef.current = null;
      }
      if (isCurrentSession()) {
        isSwitchingCameraRef.current = false;
        setSwitchingCameraState(false);
      }
    }
  }, [canSwitchCamera, refreshCameraAvailability, setCameraFacingMode, state]);

  const cleanupMedia = useCallback(() => {
    mediaSessionGenerationRef.current += 1;
    pendingCameraTrackRef.current?.stop();
    pendingCameraTrackRef.current = null;
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
    setCameraFacingMode('user');
    setCanSwitchCamera(false);
    setMicrophoneMutedState(false);
    isCameraEnabledRef.current = false;
    setCameraEnabledState(false);
    isSwitchingCameraRef.current = false;
    setSwitchingCameraState(false);
  }, [setCameraFacingMode]);

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
    setCameraFacingMode('user');
    setCanSwitchCamera(false);
    setMicrophoneMutedState(false);
    isCameraEnabledRef.current = false;
    setCameraEnabledState(false);
    isSwitchingCameraRef.current = false;
    setSwitchingCameraState(false);
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
      const videoTrack = streamRef.current?.getVideoTracks()[0];
      setCameraFacingMode(getTrackFacingMode(videoTrack, 'user'));
      void refreshCameraAvailability();
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
  }, [chatId, fail, refreshCameraAvailability, setCameraFacingMode, state]);

  useEffect(() => {
    const mediaDevices = navigator.mediaDevices;
    if (!mediaDevices?.addEventListener) {
      return;
    }

    const handleDeviceChange = () => {
      void refreshCameraAvailability();
    };
    mediaDevices.addEventListener('devicechange', handleDeviceChange);
    return () =>
      mediaDevices.removeEventListener('devicechange', handleDeviceChange);
  }, [refreshCameraAvailability]);

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
      cameraFacingMode,
      canSwitchCamera,
      isMicrophoneMuted,
      isCameraEnabled,
      isSwitchingCamera,
      setMicrophoneMuted,
      setCameraEnabled,
      switchCamera,
      start,
      stop,
    }),
    [
      cameraFacingMode,
      canSwitchCamera,
      error,
      cameraSnapshotCueSeq,
      isCameraEnabled,
      isAssistantResponsePending,
      isMicrophoneMuted,
      isSwitchingCamera,
      latestAssistantText,
      latestUserTranscript,
      localStream,
      remoteStream,
      setCameraEnabled,
      setMicrophoneMuted,
      start,
      state,
      stop,
      switchCamera,
    ],
  );
}
