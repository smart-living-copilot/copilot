import { useRef } from 'react';

import { useAttachMediaStream } from '@/components/wotbot/live-mode/use-attach-media-stream';
import { useLiveModeAudioCues } from '@/components/wotbot/live-mode/use-live-mode-audio-cues';

export function LiveModeAudioElements({
  cameraSnapshotCueSeq,
  isConnected,
  remoteStream,
}: {
  cameraSnapshotCueSeq: number;
  isConnected: boolean;
  remoteStream: MediaStream | null;
}) {
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const { readyAudioRef } = useLiveModeAudioCues({
    cameraSnapshotCueSeq,
    isConnected,
  });
  useAttachMediaStream(remoteAudioRef, remoteStream);

  return (
    <>
      <audio ref={remoteAudioRef} autoPlay />
      <audio ref={readyAudioRef} preload="auto" src="/audio/open_004.ogg" />
    </>
  );
}
