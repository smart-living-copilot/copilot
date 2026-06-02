'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Mic, Square, Volume2, VolumeX } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { useSpeechPlayback } from '@/components/jobs/speech-playback-context';
import { transcribeSpeech } from '@/lib/speech-api';

type ButtonSize = 'sm' | 'icon-sm';

export function ReadAloudButton({
  text,
  label = 'Read aloud',
  disabled = false,
  compact = false,
}: {
  text: string;
  label?: string;
  disabled?: boolean;
  compact?: boolean;
}) {
  const playbackId = useId();
  const { activeId, status, play, stop } = useSpeechPlayback();
  const isActive = activeId === playbackId;
  const isLoading = isActive && status === 'loading';
  const isPlaying = isActive && status === 'playing';

  const handleClick = useCallback(async () => {
    if (isActive) {
      stop();
      return;
    }

    const textToRead = text.trim();
    if (!textToRead) {
      toast.error('Nothing to read aloud.');
      return;
    }

    try {
      await play(playbackId, textToRead);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to create speech.',
      );
    }
  }, [isActive, play, playbackId, stop, text]);

  const size: ButtonSize = compact ? 'icon-sm' : 'sm';
  const buttonLabel = isPlaying || isLoading ? 'Stop audio' : label;

  return (
    <Button
      type="button"
      variant="outline"
      size={size}
      aria-label={buttonLabel}
      title={buttonLabel}
      disabled={disabled || !text.trim()}
      onClick={() => void handleClick()}
    >
      {isLoading ? (
        <Spinner className="size-4" />
      ) : isPlaying ? (
        <Square className="h-4 w-4" />
      ) : (
        <Volume2 className="h-4 w-4" />
      )}
      {compact ? null : <span>{isPlaying || isLoading ? 'Stop' : label}</span>}
    </Button>
  );
}

export function VoiceModeToggle() {
  const { voiceMode, toggleVoiceMode } = useSpeechPlayback();
  const label = voiceMode ? 'Voice on' : 'Voice off';

  return (
    <Button
      type="button"
      variant={voiceMode ? 'default' : 'outline'}
      onClick={toggleVoiceMode}
      aria-pressed={voiceMode}
      title={
        voiceMode
          ? 'Auto-read job updates aloud (on)'
          : 'Auto-read job updates aloud (off)'
      }
    >
      {voiceMode ? (
        <Volume2 className="h-4 w-4" />
      ) : (
        <VolumeX className="h-4 w-4" />
      )}
      {label}
    </Button>
  );
}

const MAX_RECORDING_MS = 60_000;
const METER_BARS = [
  { id: 'a', scale: 0.6 },
  { id: 'b', scale: 1 },
  { id: 'c', scale: 0.8 },
  { id: 'd', scale: 0.45 },
];

function formatClock(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function RecordingMeter({ level }: { level: number }) {
  return (
    <span className="flex items-center gap-0.5" aria-hidden>
      {METER_BARS.map((bar) => (
        <span
          key={bar.id}
          className="w-0.5 rounded-full bg-current"
          style={{
            height: `${Math.max(3, Math.min(16, level * 16 * bar.scale))}px`,
          }}
        />
      ))}
    </span>
  );
}

export function VoiceAnswerButton({
  disabled = false,
  onTranscript,
}: {
  disabled?: boolean;
  onTranscript: (text: string) => void;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [level, setLevel] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);

  const cleanupStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const stopAnalysis = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    setLevel(0);
    setElapsedSeconds(0);
  }, []);

  const stopRecording = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      cleanupStream();
      stopAnalysis();
      setIsRecording(false);
      return;
    }
    recorder.stop();
  }, [cleanupStream, stopAnalysis]);

  useEffect(() => {
    return () => {
      if (recorderRef.current?.state === 'recording') {
        recorderRef.current.stop();
      }
      cleanupStream();
      stopAnalysis();
    };
  }, [cleanupStream, stopAnalysis]);

  // Sample microphone amplitude for the live meter, surface elapsed time, and
  // auto-stop once the recording hits the max duration.
  const startAnalysis = useCallback(
    (stream: MediaStream) => {
      const AudioContextCtor =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
      if (!AudioContextCtor) return;

      const audioContext = new AudioContextCtor();
      audioContextRef.current = audioContext;
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      audioContext.createMediaStreamSource(stream).connect(analyser);
      const samples = new Uint8Array(analyser.frequencyBinCount);
      const startedAt = Date.now();

      const tick = () => {
        analyser.getByteTimeDomainData(samples);
        let sumSquares = 0;
        for (let i = 0; i < samples.length; i += 1) {
          const deviation = (samples[i] - 128) / 128;
          sumSquares += deviation * deviation;
        }
        const rms = Math.sqrt(sumSquares / samples.length);
        setLevel(Math.min(1, rms * 3));

        const elapsed = Date.now() - startedAt;
        const seconds = Math.floor(elapsed / 1000);
        setElapsedSeconds((prev) => (prev === seconds ? prev : seconds));

        if (elapsed >= MAX_RECORDING_MS) {
          stopRecording();
          return;
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    },
    [stopRecording],
  );

  const startRecording = useCallback(async () => {
    if (
      typeof navigator === 'undefined' ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === 'undefined'
    ) {
      toast.error('Voice recording is not available in this browser.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          noiseSuppression: true,
          echoCancellation: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;
      chunksRef.current = [];
      const options = MediaRecorder.isTypeSupported('audio/webm')
        ? { mimeType: 'audio/webm' }
        : undefined;
      const recorder = new MediaRecorder(stream, options);
      recorderRef.current = recorder;
      recorder.addEventListener('dataavailable', (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      });
      recorder.addEventListener(
        'stop',
        () => {
          const mimeType = recorder.mimeType || 'audio/webm';
          const audio = new Blob(chunksRef.current, { type: mimeType });
          cleanupStream();
          stopAnalysis();
          setIsRecording(false);
          if (audio.size === 0) {
            toast.error('No audio was captured.');
            chunksRef.current = [];
            recorderRef.current = null;
            return;
          }
          setIsTranscribing(true);
          void transcribeSpeech(audio)
            .then((text) => {
              if (!text) {
                toast.error('No speech was transcribed.');
                return;
              }
              onTranscript(text);
              toast.success('Voice answer transcribed.');
            })
            .catch((error) => {
              toast.error(
                error instanceof Error
                  ? error.message
                  : 'Failed to transcribe answer.',
              );
            })
            .finally(() => {
              setIsTranscribing(false);
              chunksRef.current = [];
              recorderRef.current = null;
            });
        },
        { once: true },
      );
      recorder.start();
      setIsRecording(true);
      startAnalysis(stream);
    } catch (error) {
      cleanupStream();
      stopAnalysis();
      toast.error(
        error instanceof Error ? error.message : 'Failed to start recording.',
      );
    }
  }, [cleanupStream, onTranscript, startAnalysis, stopAnalysis]);

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      disabled={disabled || isTranscribing}
      aria-label={isRecording ? 'Stop recording' : 'Dictate answer'}
      onClick={() => {
        if (isRecording) {
          stopRecording();
        } else {
          void startRecording();
        }
      }}
    >
      {isTranscribing ? (
        <Spinner className="size-4" />
      ) : isRecording ? (
        <RecordingMeter level={level} />
      ) : (
        <Mic className="h-4 w-4" />
      )}
      {isRecording
        ? formatClock(elapsedSeconds)
        : isTranscribing
          ? 'Transcribing'
          : 'Dictate'}
    </Button>
  );
}
