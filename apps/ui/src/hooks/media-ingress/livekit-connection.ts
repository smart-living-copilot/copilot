import { Room, RoomEvent, Track } from 'livekit-client';

import { requestLiveKitAgentDispatch } from '@/hooks/media-ingress/livekit-api';
import {
  cloneMediaStream,
  liveKitParticipantLooksLikeAgent,
  liveKitSourceForTrack,
  logMediaConnectionStep,
} from '@/hooks/media-ingress/livekit-utils';
import {
  type LiveKitParticipantInfo,
  type LiveKitTextStreamReader,
  type LiveKitTokenResponse,
  type MediaIngressState,
} from '@/hooks/media-ingress/types';

type MutableRef<T> = {
  current: T;
};

interface StartLiveKitConnectionOptions {
  chatId: string;
  connection: LiveKitTokenResponse;
  fail: (message: string) => void;
  liveKitRemoteStreamRef: MutableRef<MediaStream | null>;
  liveKitRoomRef: MutableRef<Room | null>;
  setAssistantResponsePending: (pending: boolean) => void;
  setLatestAssistantText: (text: string | null) => void;
  setLatestUserTranscript: (text: string | null) => void;
  setLocalStream: (stream: MediaStream | null) => void;
  setRemoteStream: (stream: MediaStream | null) => void;
  setState: (state: MediaIngressState) => void;
  startedAt: number;
  streamRef: MutableRef<MediaStream | null>;
}

export async function startLiveKitConnection({
  chatId,
  connection,
  fail,
  liveKitRemoteStreamRef,
  liveKitRoomRef,
  setAssistantResponsePending,
  setLatestAssistantText,
  setLatestUserTranscript,
  setLocalStream,
  setRemoteStream,
  setState,
  startedAt,
  streamRef,
}: StartLiveKitConnectionOptions) {
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
    if (track.kind !== Track.Kind.Audio && track.kind !== Track.Kind.Video) {
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
    if (track.kind !== Track.Kind.Audio && track.kind !== Track.Kind.Video) {
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
          // Clear the previous answer so the pending indicator (thinking dots +
          // waiting sound) shows again for this new turn, not just the first one.
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
}
