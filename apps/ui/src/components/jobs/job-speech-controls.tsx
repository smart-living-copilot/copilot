'use client';

import { useCallback, useId } from 'react';
import { Mic, Square, Volume2, VolumeX } from 'lucide-react';
import { toast } from 'sonner';

import { RecordingMeter } from '@/components/jobs/speech/recording-meter';
import { useVoiceAnswerRecorder } from '@/components/jobs/speech/use-voice-answer-recorder';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { useSpeechPlayback } from '@/components/jobs/speech-playback-context';

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

function formatClock(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

export function VoiceAnswerButton({
  disabled = false,
  onTranscript,
}: {
  disabled?: boolean;
  onTranscript: (text: string) => void;
}) {
  const {
    elapsedSeconds,
    isRecording,
    isTranscribing,
    level,
    startRecording,
    stopRecording,
  } = useVoiceAnswerRecorder({ onTranscript });

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
