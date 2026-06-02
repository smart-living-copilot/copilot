'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Mic, Square, Volume2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { synthesizeSpeech, transcribeSpeech } from '@/lib/speech-api';

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
  const [isLoading, setIsLoading] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
      audioRef.current = null;
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
    setIsPlaying(false);
    setIsLoading(false);
  }, []);

  useEffect(() => stop, [stop]);

  const handleClick = useCallback(async () => {
    if (isPlaying || isLoading) {
      stop();
      return;
    }

    const textToRead = text.trim();
    if (!textToRead) {
      toast.error('Nothing to read aloud.');
      return;
    }

    setIsLoading(true);
    try {
      const blob = await synthesizeSpeech(textToRead.slice(0, 4096));
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioUrlRef.current = url;
      audioRef.current = audio;
      audio.addEventListener('ended', stop, { once: true });
      audio.addEventListener(
        'error',
        () => {
          toast.error('Failed to play speech audio.');
          stop();
        },
        { once: true },
      );
      setIsPlaying(true);
      setIsLoading(false);
      await audio.play();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to create speech.',
      );
      stop();
    }
  }, [isLoading, isPlaying, stop, text]);

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
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : isPlaying ? (
        <Square className="h-4 w-4" />
      ) : (
        <Volume2 className="h-4 w-4" />
      )}
      {compact ? null : <span>{isPlaying || isLoading ? 'Stop' : label}</span>}
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
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : isRecording ? (
        <Square className="h-4 w-4" />
      ) : (
        <Mic className="h-4 w-4" />
      )}
      {isBusy ? label : 'Dictate'}
    </Button>
  );
}
