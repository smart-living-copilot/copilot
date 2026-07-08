import { useRef } from 'react';
import { VideoOff } from 'lucide-react';

import { useAttachMediaStream } from '@/components/wotbot/live-mode/use-attach-media-stream';

export function LiveModeCameraPreview({
  inViewer,
  isCameraEnabled,
  localStream,
}: {
  inViewer: boolean;
  isCameraEnabled: boolean;
  localStream: MediaStream | null;
}) {
  const previewRef = useRef<HTMLVideoElement | null>(null);
  useAttachMediaStream(previewRef, localStream);

  if (!localStream) {
    return null;
  }

  return (
    <div
      className={
        inViewer
          ? 'absolute right-3 top-3 z-10 h-12 w-16 overflow-hidden rounded-lg border border-border bg-muted shadow-md md:right-4 md:top-4 md:h-14 md:w-20'
          : 'absolute right-3 top-3 z-10 h-20 w-28 overflow-hidden rounded-xl border border-border bg-muted shadow-lg md:right-4 md:top-4 md:h-24 md:w-36'
      }
    >
      <video
        ref={previewRef}
        autoPlay
        className={
          isCameraEnabled
            ? 'h-full w-full object-cover'
            : 'h-full w-full object-cover opacity-0'
        }
        muted
        playsInline
      />
      {!isCameraEnabled ? (
        <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
          <VideoOff className={inViewer ? 'size-3.5' : 'size-5'} />
        </div>
      ) : null}
    </div>
  );
}
