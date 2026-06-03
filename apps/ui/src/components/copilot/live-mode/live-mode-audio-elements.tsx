import { useRef } from 'react';

import { useAttachMediaStream } from '@/components/copilot/live-mode/use-attach-media-stream';
import { useLiveModeAudioCues } from '@/components/copilot/live-mode/use-live-mode-audio-cues';

export function LiveModeAudioElements({
  isConnected,
  remoteStream,
  showAssistantPending,
}: {
  isConnected: boolean;
  remoteStream: MediaStream | null;
  showAssistantPending: boolean;
}) {
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const { readyAudioRef, waitingAudioRef } = useLiveModeAudioCues({
    isConnected,
    showAssistantPending,
  });
  useAttachMediaStream(remoteAudioRef, remoteStream);

  return (
    <>
      <audio ref={remoteAudioRef} autoPlay />
      <audio ref={readyAudioRef} preload="auto" src="/audio/open_004.ogg" />
      <audio ref={waitingAudioRef} preload="auto" src="/audio/switch_007.ogg" />
    </>
  );
}
