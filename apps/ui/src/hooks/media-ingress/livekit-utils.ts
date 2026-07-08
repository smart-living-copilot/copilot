import { Track } from 'livekit-client';

import { type LiveKitParticipantInfo } from '@/hooks/media-ingress/types';

export function logMediaConnectionStep(
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

export function cloneMediaStream(stream: MediaStream) {
  return new MediaStream(stream.getTracks());
}

export function liveKitParticipantLooksLikeAgent(
  participantInfo: LiveKitParticipantInfo,
) {
  const identity = participantInfo.identity?.toLowerCase() || '';
  const kind = String(participantInfo.kind ?? '').toLowerCase();
  return (
    kind.includes('agent') ||
    identity.startsWith('agent-') ||
    identity.includes('wotbot')
  );
}

export function liveKitSourceForTrack(track: MediaStreamTrack) {
  if (track.kind === 'audio') {
    return Track.Source.Microphone;
  }
  if (track.kind === 'video') {
    return Track.Source.Camera;
  }
  return Track.Source.Unknown;
}
