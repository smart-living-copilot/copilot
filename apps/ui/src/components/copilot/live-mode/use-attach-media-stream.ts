import { useEffect, type RefObject } from 'react';

export function useAttachMediaStream<TElement extends HTMLMediaElement>(
  mediaRef: RefObject<TElement | null>,
  stream: MediaStream | null,
) {
  useEffect(() => {
    const media = mediaRef.current;
    if (!media) {
      return;
    }

    media.srcObject = stream;
    if (stream) {
      void media.play().catch(() => {
        // Autoplay can be browser-policy dependent; live media remains connected.
      });
    }

    return () => {
      media.srcObject = null;
    };
  }, [stream, mediaRef]);
}
