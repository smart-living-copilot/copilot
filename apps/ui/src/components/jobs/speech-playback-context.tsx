'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';

import { synthesizeSpeech } from '@/lib/speech-api';

const VOICE_MODE_KEY = 'jobs:voice-mode';
const TTS_MAX_CHARS = 4096;

function storedVoiceMode(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(VOICE_MODE_KEY) === 'true';
  } catch {
    return false;
  }
}

const voiceModeListeners = new Set<() => void>();

function subscribeVoiceMode(callback: () => void): () => void {
  voiceModeListeners.add(callback);
  return () => {
    voiceModeListeners.delete(callback);
  };
}

function setStoredVoiceMode(next: boolean): void {
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(VOICE_MODE_KEY, String(next));
    } catch {
      // Preference persistence is best-effort.
    }
  }
  for (const listener of voiceModeListeners) {
    listener();
  }
}

type PlaybackStatus = 'idle' | 'loading' | 'playing';

interface SpeechPlaybackValue {
  /** Id of the text currently loading or playing, or null when idle. */
  activeId: string | null;
  status: PlaybackStatus;
  /** Auto-speak incoming job questions/results when enabled. */
  voiceMode: boolean;
  /** Synthesize and play `text`, stopping any current playback first. */
  play: (id: string, text: string) => Promise<void>;
  stop: () => void;
  toggleVoiceMode: () => void;
}

const SpeechPlaybackContext = createContext<SpeechPlaybackValue | null>(null);

export function useSpeechPlayback(): SpeechPlaybackValue {
  const ctx = useContext(SpeechPlaybackContext);
  if (!ctx) {
    throw new Error(
      'useSpeechPlayback must be used inside SpeechPlaybackProvider',
    );
  }
  return ctx;
}

/**
 * Build a short silent WAV clip used to unlock audio playback inside a user
 * gesture. Browsers block programmatic `audio.play()` from background events
 * (e.g. job toasts) unless the element has been played from a gesture first.
 */
let silentAudioUrl: string | null = null;
function getSilentAudioUrl(): string {
  if (silentAudioUrl) return silentAudioUrl;
  const sampleRate = 8000;
  const numSamples = 400; // ~50ms
  const buffer = new ArrayBuffer(44 + numSamples);
  const view = new DataView(buffer);
  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + numSamples, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate, true);
  view.setUint16(32, 1, true);
  view.setUint16(34, 8, true); // 8-bit
  writeString(36, 'data');
  view.setUint32(40, numSamples, true);
  for (let i = 0; i < numSamples; i += 1) {
    view.setUint8(44 + i, 128); // 8-bit PCM silence is centered at 128
  }
  silentAudioUrl = URL.createObjectURL(
    new Blob([buffer], { type: 'audio/wav' }),
  );
  return silentAudioUrl;
}

export function SpeechPlaybackProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [status, setStatus] = useState<PlaybackStatus>('idle');
  // Persisted preference read through an external store so the first client
  // render matches the server HTML (false) without a setState-in-effect.
  const voiceMode = useSyncExternalStore(
    subscribeVoiceMode,
    storedVoiceMode,
    () => false,
  );

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  // Monotonic token so an in-flight synthesis can detect it was superseded.
  const playTokenRef = useRef(0);

  const ensureAudio = useCallback(() => {
    if (!audioRef.current) {
      audioRef.current = new Audio();
    }
    return audioRef.current;
  }, []);

  const revokeUrl = useCallback(() => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    revokeUrl();
    setActiveId(null);
    setStatus('idle');
  }, [revokeUrl]);

  const stop = useCallback(() => {
    playTokenRef.current += 1; // invalidate any in-flight synthesis
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
    }
    reset();
  }, [reset]);

  const play = useCallback(
    async (id: string, text: string) => {
      const content = text.trim();
      if (!content) return;

      const token = (playTokenRef.current += 1);
      const audio = ensureAudio();
      audio.pause();
      revokeUrl();
      audio.muted = false;
      setActiveId(id);
      setStatus('loading');

      try {
        const blob = await synthesizeSpeech(content.slice(0, TTS_MAX_CHARS));
        if (playTokenRef.current !== token) return; // superseded by a newer play
        const url = URL.createObjectURL(blob);
        objectUrlRef.current = url;
        audio.src = url;
        audio.onended = () => {
          if (playTokenRef.current === token) reset();
        };
        audio.onerror = () => {
          if (playTokenRef.current === token) reset();
        };
        await audio.play();
        if (playTokenRef.current === token) setStatus('playing');
      } catch (error) {
        if (playTokenRef.current === token) reset();
        throw error;
      }
    },
    [ensureAudio, reset, revokeUrl],
  );

  const unlock = useCallback(() => {
    // Must run synchronously inside a user gesture to grant autoplay later.
    const audio = ensureAudio();
    try {
      audio.muted = true;
      audio.src = getSilentAudioUrl();
      void audio.play().catch(() => {});
    } catch {
      // ignore — autoplay will simply require a manual tap
    }
  }, [ensureAudio]);

  const toggleVoiceMode = useCallback(() => {
    const next = !storedVoiceMode();
    if (next) unlock();
    setStoredVoiceMode(next);
  }, [unlock]);

  useEffect(() => () => stop(), [stop]);

  const value = useMemo(
    () => ({ activeId, status, voiceMode, play, stop, toggleVoiceMode }),
    [activeId, status, voiceMode, play, stop, toggleVoiceMode],
  );

  return (
    <SpeechPlaybackContext.Provider value={value}>
      {children}
    </SpeechPlaybackContext.Provider>
  );
}
