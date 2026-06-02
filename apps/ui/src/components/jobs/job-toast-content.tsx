'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from 'react';
import { BarChart3, Send } from 'lucide-react';
import { toast } from 'sonner';

import {
  ReadAloudButton,
  VoiceAnswerButton,
} from '@/components/jobs/job-speech-controls';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { Textarea } from '@/components/ui/textarea';
import {
  formatArtifactSummary,
  type RunCodeArtifact,
} from '@/components/copilot/chat-tool-call-model';
import { hasCodeOutput, normalizeJobCodeResult } from '@/lib/job-code-result';
import {
  createClientReplyId,
  fetchJobRuns,
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
      ) : (
        <JobToastArtifacts job={job} onOpen={onOpen} />
      )}
    </div>
  );
}

/**
 * Lazily fetch the latest run for a finished job and, when it produced chart or
 * image artifacts, surface a compact preview in the toast. Image artifacts get
 * an inline thumbnail; charts fall back to a summary line. Clicking opens the
 * job detail page where the full interactive artifacts live.
 */
function JobToastArtifacts({
  job,
  onOpen,
}: {
  job: JobRecord;
  onOpen: () => void;
}) {
  const [artifacts, setArtifacts] = useState<RunCodeArtifact[]>([]);

  useEffect(() => {
    if (job.last_run_status !== 'succeeded' || !job.last_run_id) return;

    let active = true;
    void fetchJobRuns(job.id)
      .then((runs) => {
        if (!active) return;
        const latest = runs.find((run) =>
          hasCodeOutput(normalizeJobCodeResult(run.result)),
        );
        const result = latest ? normalizeJobCodeResult(latest.result) : null;
        setArtifacts(result?.artifacts ?? []);
      })
      .catch(() => {
        // Best-effort enrichment; the toast is still useful without it.
      });

    return () => {
      active = false;
    };
  }, [job.id, job.last_run_id, job.last_run_status]);

  if (artifacts.length === 0) return null;

  const imageArtifact = artifacts.find((artifact) => artifact.kind === 'image');

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group block w-full space-y-1.5 text-left"
    >
      {imageArtifact ? (
        // eslint-disable-next-line @next/next/no-img-element -- generated artifacts are proxied files and skip Next image optimization
        <img
          alt={imageArtifact.ref}
          src={`/api/artifacts/${encodeURIComponent(imageArtifact.filename)}`}
          className="max-h-44 w-full rounded-md border border-border/60 bg-muted/20 object-contain transition group-hover:border-border"
        />
      ) : null}
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <BarChart3 className="size-3.5" />
        {formatArtifactSummary(artifacts)} · View details
      </span>
    </button>
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
            <Spinner className="size-4" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          Submit
        </Button>
      </div>
    </form>
  );
}
