'use client';

import { AudioLines } from 'lucide-react';
import {
  useEffect,
  useMemo,
  useState,
  type ComponentProps,
  type CSSProperties,
  type ReactNode,
} from 'react';
import type { MediaIngressState } from '@/hooks/use-media-ingress-session';
import { cn } from '@/lib/utils';

type AuraSize = 'sm' | 'md' | 'lg' | 'xl';

const SIZE_CLASS: Record<AuraSize, string> = {
  sm: 'size-28',
  md: 'size-40',
  lg: 'size-52 md:size-60',
  xl: 'size-60 md:size-72',
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function useMediaStreamLevel(stream: MediaStream | null, enabled: boolean) {
  const [level, setLevel] = useState(0);

  useEffect(() => {
    if (!stream || !enabled || stream.getAudioTracks().length === 0) {
      const resetFrame = window.requestAnimationFrame(() => setLevel(0));
      return () => window.cancelAnimationFrame(resetFrame);
    }

    let animationFrame = 0;
    let closed = false;
    let smoothedLevel = 0;
    let lastRenderedLevel = 0;
    const AudioContextConstructor = window.AudioContext;
    const audioContext = new AudioContextConstructor();
    const analyser = audioContext.createAnalyser();
    const source = audioContext.createMediaStreamSource(stream);

    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.72;
    const samples = new Uint8Array(analyser.fftSize);
    source.connect(analyser);

    void audioContext.resume().catch(() => {
      // The aura can still idle if the browser keeps the audio context suspended.
    });

    const tick = () => {
      analyser.getByteTimeDomainData(samples);

      let sum = 0;
      for (const sample of samples) {
        const centered = (sample - 128) / 128;
        sum += centered * centered;
      }

      const rms = Math.sqrt(sum / samples.length);
      const nextLevel = clamp(rms * 5, 0, 1);
      smoothedLevel += (nextLevel - smoothedLevel) * 0.22;

      if (Math.abs(smoothedLevel - lastRenderedLevel) > 0.012) {
        lastRenderedLevel = smoothedLevel;
        setLevel(smoothedLevel);
      }

      if (!closed) {
        animationFrame = window.requestAnimationFrame(tick);
      }
    };

    tick();

    return () => {
      closed = true;
      window.cancelAnimationFrame(animationFrame);
      source.disconnect();
      analyser.disconnect();
      void audioContext.close().catch(() => {
        // Closing is best-effort across browser implementations.
      });
      setLevel(0);
    };
  }, [enabled, stream]);

  return level;
}

function stateActivity(state: MediaIngressState) {
  if (state === 'connected') {
    return 0.2;
  }
  if (state === 'requesting' || state === 'connecting') {
    return 0.34;
  }
  if (state === 'error') {
    return 0.08;
  }
  return 0.12;
}

export function MediaStreamAura({
  stream,
  state,
  icon,
  size = 'lg',
  className,
  ...props
}: {
  stream: MediaStream | null;
  state: MediaIngressState;
  icon?: ReactNode;
  size?: AuraSize;
} & ComponentProps<'div'>) {
  const isConnected = state === 'connected';
  const level = useMediaStreamLevel(stream, isConnected);
  const intensity = clamp(Math.max(level, stateActivity(state)), 0, 1);
  const style = useMemo(
    () =>
      ({
        '--live-aura-level': intensity.toFixed(3),
        '--live-aura-scale': (0.82 + intensity * 0.32).toFixed(3),
        '--live-aura-opacity': (0.5 + intensity * 0.38).toFixed(3),
      }) as CSSProperties,
    [intensity],
  );

  return (
    <div
      className={cn(
        'live-mode-aura relative grid aspect-square place-items-center',
        SIZE_CLASS[size],
        className,
      )}
      data-state={state}
      style={style}
      {...props}
    >
      <div className="live-mode-aura__halo" />
      <div className="live-mode-aura__field">
        <span className="live-mode-aura__lobe live-mode-aura__lobe--one" />
        <span className="live-mode-aura__lobe live-mode-aura__lobe--two" />
        <span className="live-mode-aura__lobe live-mode-aura__lobe--three" />
      </div>
      <div className="live-mode-aura__ring live-mode-aura__ring--outer" />
      <div className="live-mode-aura__ring live-mode-aura__ring--inner" />
      <div className="live-mode-aura__core">
        {icon ?? <AudioLines className="size-6" />}
      </div>
    </div>
  );
}
