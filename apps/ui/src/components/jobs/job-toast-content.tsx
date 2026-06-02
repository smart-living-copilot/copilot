'use client';

import { useCallback, useRef, useState, type FormEvent } from 'react';
import { Loader2, Send } from 'lucide-react';
import { toast } from 'sonner';

import {
  ReadAloudButton,
  VoiceAnswerButton,
} from '@/components/jobs/job-speech-controls';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  createClientReplyId,
  replyToJob,
  type JobRecord,
} from '@/lib/jobs-api';

/**
 * Rich body rendered inside a job event toast. Shows the run summary, a
 * read-aloud (TTS) control, and — for prompt jobs waiting on human feedback —
 * an inline answer form with voice dictation (STT) so the loop can be closed
 * without leaving the page.
 */
export function JobToastContent({
  job,
  detail,
  onOpen,
  onAnswered,
}: {
  job: JobRecord;
  detail: string;
  onOpen: () => void;
  onAnswered: () => void;
}) {
  const isWaiting = job.last_run_status === 'waiting_for_input';

  return (
    <div className="space-y-2.5">
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          className="cursor-pointer text-left text-sm leading-5"
          onClick={onOpen}
        >
          {detail}
        </button>
        <ReadAloudButton text={detail} compact />
      </div>
      {isWaiting ? (
        <JobToastAnswerForm job={job} onAnswered={onAnswered} />
      ) : null}
    </div>
  );
}

function JobToastAnswerForm({
  job,
  onAnswered,
}: {
  job: JobRecord;
  onAnswered: () => void;
}) {
  const [value, setValue] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const pendingReplyRef = useRef<{
    message: string;
    clientReplyId: string;
  } | null>(null);

  const handleVoiceAnswer = useCallback((message: string) => {
    setValue((current) => {
      const currentText = current.trim();
      return currentText ? `${currentText} ${message}` : message;
    });
  }, []);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const message = value.trim();
      if (!message || isSubmitting) return;

      let pendingReply = pendingReplyRef.current;
      if (!pendingReply || pendingReply.message !== message) {
        pendingReply = { message, clientReplyId: createClientReplyId() };
        pendingReplyRef.current = pendingReply;
      }

      setIsSubmitting(true);
      try {
        await replyToJob(job.id, message, pendingReply.clientReplyId);
        pendingReplyRef.current = null;
        toast.success('Answer submitted.');
        onAnswered();
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to submit answer',
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [isSubmitting, job.id, onAnswered, value],
  );

  const canSubmit = value.trim().length > 0 && !isSubmitting;

  return (
    <form className="space-y-2" onSubmit={handleSubmit}>
      <Textarea
        aria-label="Job answer"
        className="min-h-16 resize-y text-sm"
        placeholder="Answer..."
        value={value}
        onChange={(event) => setValue(event.target.value)}
        disabled={isSubmitting}
      />
      <div className="flex items-center justify-end gap-2">
        <VoiceAnswerButton
          disabled={isSubmitting}
          onTranscript={handleVoiceAnswer}
        />
        <Button type="submit" size="sm" disabled={!canSubmit}>
          {isSubmitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          Submit
        </Button>
      </div>
    </form>
  );
}
