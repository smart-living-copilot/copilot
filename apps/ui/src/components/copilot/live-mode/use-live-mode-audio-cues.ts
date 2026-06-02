import { useEffect, useRef } from 'react';

const WAITING_AUDIO_REPEAT_DELAY_MS = 1200;

export function useLiveModeAudioCues({
  isConnected,
  showAssistantPending,
}: {
  isConnected: boolean;
  showAssistantPending: boolean;
}) {
  const readyAudioRef = useRef<HTMLAudioElement | null>(null);
  const waitingAudioRef = useRef<HTMLAudioElement | null>(null);
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
    const audio = waitingAudioRef.current;
    if (!audio) {
      return;
    }

    if (!showAssistantPending) {
      audio.pause();
      audio.currentTime = 0;
      return;
    }

    let repeatTimer: number | null = null;
    let stopped = false;
    const playWaitingAudio = () => {
      if (stopped) {
        return;
      }
      audio.currentTime = 0;
      void audio.play().catch(() => {
        // Browser autoplay policies can still block this despite the start click.
      });
    };
    const scheduleRepeat = () => {
      if (stopped) {
        return;
      }
      repeatTimer = window.setTimeout(
        playWaitingAudio,
        WAITING_AUDIO_REPEAT_DELAY_MS,
      );
    };

    audio.addEventListener('ended', scheduleRepeat);
    playWaitingAudio();

    return () => {
      stopped = true;
      if (repeatTimer !== null) {
        window.clearTimeout(repeatTimer);
      }
      audio.removeEventListener('ended', scheduleRepeat);
      audio.pause();
      audio.currentTime = 0;
    };
  }, [showAssistantPending]);

  return {
    readyAudioRef,
    waitingAudioRef,
  };
}
