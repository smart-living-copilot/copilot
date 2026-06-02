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

export function VoiceAnswerButton({
  disabled = false,
  onTranscript,
}: {
  disabled?: boolean;
  onTranscript: (text: string) => void;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  const cleanupStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const stopRecording = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      cleanupStream();
      setIsRecording(false);
      return;
    }
    recorder.stop();
  }, [cleanupStream]);

  useEffect(() => {
    return () => {
      if (recorderRef.current?.state === 'recording') {
        recorderRef.current.stop();
      }
      cleanupStream();
    };
  }, [cleanupStream]);

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
    } catch (error) {
      cleanupStream();
      toast.error(
        error instanceof Error ? error.message : 'Failed to start recording.',
      );
    }
  }, [cleanupStream, onTranscript]);

  const isBusy = isRecording || isTranscribing;
  const label = isRecording
    ? 'Stop recording'
    : isTranscribing
      ? 'Transcribing'
      : 'Dictate answer';

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      disabled={disabled || isTranscribing}
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
        <Square className="h-4 w-4" />
      ) : (
        <Mic className="h-4 w-4" />
      )}
      {isBusy ? label : 'Dictate'}
    </Button>
  );
}
