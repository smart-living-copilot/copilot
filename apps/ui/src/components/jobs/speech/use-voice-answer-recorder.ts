'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import { transcribeSpeech } from '@/lib/speech-api';

const MAX_RECORDING_MS = 60_000;

interface UseVoiceAnswerRecorderOptions {
  onTranscript: (text: string) => void;
}

export function useVoiceAnswerRecorder({
  onTranscript,
}: UseVoiceAnswerRecorderOptions) {
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

  return {
    elapsedSeconds,
    isRecording,
    isTranscribing,
    level,
    startRecording,
    stopRecording,
  };
}
