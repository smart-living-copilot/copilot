import { useEffect, useRef } from 'react';

function playClick(
  context: AudioContext,
  startAt: number,
  frequency: number,
  duration: number,
  volume: number,
) {
  const oscillator = context.createOscillator();
  const gain = context.createGain();

  oscillator.type = 'square';
  oscillator.frequency.setValueAtTime(frequency, startAt);
  gain.gain.setValueAtTime(0.0001, startAt);
  gain.gain.exponentialRampToValueAtTime(volume, startAt + 0.006);
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);

  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start(startAt);
  oscillator.stop(startAt + duration + 0.01);
}

export function useLiveModeAudioCues({
  cameraSnapshotCueSeq,
  isConnected,
}: {
  cameraSnapshotCueSeq: number;
  isConnected: boolean;
}) {
  const readyAudioRef = useRef<HTMLAudioElement | null>(null);
  const snapshotAudioContextRef = useRef<AudioContext | null>(null);
  const lastSnapshotCueSeqRef = useRef(cameraSnapshotCueSeq);
  const wasConnectedRef = useRef(false);

  useEffect(() => {
    const wasConnected = wasConnectedRef.current;
    wasConnectedRef.current = isConnected;
    if (!isConnected || wasConnected) {
      return;
    }

    const audio = readyAudioRef.current;
    if (!audio) {
      return;
    }

    audio.currentTime = 0;
    void audio.play().catch(() => {
      // Browser autoplay policies can still block this despite the start click.
    });
  }, [isConnected]);

  useEffect(() => {
    if (
      cameraSnapshotCueSeq <= 0 ||
      cameraSnapshotCueSeq === lastSnapshotCueSeqRef.current
    ) {
      lastSnapshotCueSeqRef.current = cameraSnapshotCueSeq;
      return;
    }
    lastSnapshotCueSeqRef.current = cameraSnapshotCueSeq;

    const AudioContextConstructor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!AudioContextConstructor) {
      return;
    }

    const context =
      snapshotAudioContextRef.current ?? new AudioContextConstructor();
    snapshotAudioContextRef.current = context;

    const playSnapshotCue = () => {
      const startAt = context.currentTime + 0.015;
      playClick(context, startAt, 1350, 0.035, 0.08);
      playClick(context, startAt + 0.055, 850, 0.045, 0.06);
    };

    if (context.state === 'suspended') {
      void context
        .resume()
        .then(playSnapshotCue)
        .catch(() => {
          // Browser autoplay policies can still block this despite the start click.
        });
      return;
    }

    playSnapshotCue();
  }, [cameraSnapshotCueSeq]);

  useEffect(
    () => () => {
      const context = snapshotAudioContextRef.current;
      snapshotAudioContextRef.current = null;
      if (context) {
        void context.close().catch(() => {
          // Some browsers reject close() if the context is already closing.
        });
      }
    },
    [],
  );

  return {
    readyAudioRef,
  };
}
