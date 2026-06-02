'use client';

import {
  CopilotChatConfigurationProvider,
  CopilotKitProvider,
  CopilotChatView,
  type Message,
} from '@copilotkit/react-core/v2';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react';
import Link from 'next/link';
import {
  Bot,
  CheckCircle2,
  CircleDot,
  ClipboardCheck,
  Eye,
  MessageSquare,
  MessageSquareReply,
  RefreshCw,
  Send,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';

import { JobRunHistoryCard } from '@/components/jobs/job-run-history';
import {
  ReadAloudButton,
  VoiceAnswerButton,
} from '@/components/jobs/job-speech-controls';
import { LiveModePanel } from '@/components/copilot/live-mode-panel';
import { chatToolCallRenderers } from '@/components/copilot/chat-tool-call-renderer';
import { MessageViewWithWotSummary } from '@/components/copilot/wot-interaction-summary';
import {
  formatArtifactSummary,
  normalizeRunCodeResult,
  type RunCodeResult,
} from '@/components/copilot/chat-tool-call-model';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Spinner } from '@/components/ui/spinner';
import { Textarea } from '@/components/ui/textarea';
import { useJobEvents } from '@/hooks/use-job-events';
import { useMediaIngressSession } from '@/hooks/use-media-ingress-session';
import {
  getJobStatus,
  getScheduleLabel,
  getSubmittedRecordResultSummary,
  getStatusBadgeVariant,
  getStatusLabel,
  supportsJobReply,
  supportsJobThread,
} from '@/lib/job-formatters';
import {
  type JobRecord,
  type JobRunEventRecord,
  type JobRunEventType,
  type JobRunRecord,
  type JobThreadRecord,
  createClientReplyId,
  fetchJobRuns,
  fetchJobThread,
  replyToJob,
} from '@/lib/jobs-api';

interface JobThreadPageProps {
  jobId: string;
}

type LoadOptions = {
  silent?: boolean;
};

function normalizeMessages(thread: JobThreadRecord | null): Message[] {
  return (thread?.messages ?? []).map((message, index) => {
    return {
      ...message,
      id: message.id ?? `job-message-${index}`,
    } as Message;
  });
}

function runOutcome(run: JobRunRecord): string {
  const codeResult = normalizeJobCodeResult(run.result);
  const artifactSummary = codeResult.artifacts?.length
    ? formatArtifactSummary(codeResult.artifacts)
    : '';
  if (artifactSummary && codeResult.stdout?.trim()) {
    return `${artifactSummary} • text output`;
  }
  if (artifactSummary) return artifactSummary;
  if (codeResult.stdout?.trim()) return codeResult.stdout.trim();
  if (codeResult.error?.trim()) return codeResult.error.trim();
  if (run.error?.trim()) return run.error.trim();
  const submittedRecordSummary = getSubmittedRecordResultSummary(run.result);
  if (submittedRecordSummary) return submittedRecordSummary;
  if (run.response_text?.trim()) return run.response_text.trim();
  if (run.result != null) {
    try {
      return JSON.stringify(run.result, null, 2);
    } catch {
      return String(run.result);
    }
  }
  return 'No output captured.';
}

function hasCodeOutput(result: RunCodeResult): boolean {
  return Boolean(
    result.error?.trim() ||
    result.stdout?.trim() ||
    (result.artifacts?.length ?? 0) > 0,
  );
}

function normalizeJobCodeResult(value: unknown): RunCodeResult {
  const direct = normalizeRunCodeResult(value);
  if (hasCodeOutput(direct)) {
    return direct;
  }

  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return direct;
  }

  return normalizeRunCodeResult((value as { response?: unknown }).response);
}

function eventLabel(type: JobRunEventType): string {
  switch (type) {
    case 'run_started':
      return 'Started';
    case 'user_reply':
      return 'Reply';
    case 'waiting_for_input':
      return 'Waiting';
    case 'assistant_message':
      return 'Assistant';
    case 'record_submitted':
      return 'Record';
    case 'run_succeeded':
      return 'Succeeded';
    case 'run_failed':
      return 'Failed';
    case 'run_cancelled':
      return 'Cancelled';
    case 'run_skipped':
      return 'Skipped';
  }
}

function eventIcon(type: JobRunEventType) {
  switch (type) {
    case 'run_succeeded':
      return <CheckCircle2 className="h-4 w-4 text-emerald-600" />;
    case 'run_failed':
    case 'run_cancelled':
      return <XCircle className="h-4 w-4 text-destructive" />;
    case 'user_reply':
      return <MessageSquare className="h-4 w-4 text-sky-600" />;
    case 'assistant_message':
    case 'waiting_for_input':
      return <Bot className="h-4 w-4 text-primary" />;
    case 'record_submitted':
      return <ClipboardCheck className="h-4 w-4 text-emerald-600" />;
    default:
      return <CircleDot className="h-4 w-4 text-muted-foreground" />;
  }
}

function eventFallbackMessage(type: JobRunEventType): string {
  switch (type) {
    case 'run_started':
      return 'Run started.';
    case 'record_submitted':
      return 'Structured record submitted.';
    case 'run_succeeded':
      return 'Run succeeded.';
    case 'run_failed':
      return 'Run failed.';
    case 'run_cancelled':
      return 'Run cancelled.';
    case 'run_skipped':
      return 'Run skipped.';
    case 'waiting_for_input':
      return 'Waiting for input.';
    case 'user_reply':
      return 'Reply received.';
    case 'assistant_message':
      return 'Assistant response.';
  }
}

function formatEventTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function payloadPreview(payload: unknown): string | null {
  if (payload == null) return null;
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

function JobEventTimeline({ events }: { events: JobRunEventRecord[] }) {
  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold tracking-tight">Timeline</h2>
          <Badge variant="outline">{events.length} events</Badge>
        </div>
        <div className="divide-y rounded-md border bg-background">
          {events.map((event) => {
            const preview =
              event.event_type === 'record_submitted'
                ? payloadPreview(event.payload)
                : null;
            return (
              <div
                key={event.id}
                className="grid grid-cols-[2rem_1fr] gap-3 px-4 py-3"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-md border bg-muted/30">
                  {eventIcon(event.event_type)}
                </div>
                <div className="min-w-0 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">
                      {eventLabel(event.event_type)}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {formatEventTime(event.created_at)}
                    </span>
                  </div>
                  <p className="whitespace-pre-wrap break-words text-sm leading-6 text-foreground">
                    {event.message || eventFallbackMessage(event.event_type)}
                  </p>
                  {preview ? (
                    <pre className="max-h-64 overflow-auto rounded-md bg-muted/30 p-3 text-xs leading-5 text-muted-foreground">
                      {preview}
                    </pre>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function WaitingReplyCard({
  question,
  value,
  isSubmitting,
  detailsHref,
  onChange,
  onVoiceAnswer,
  onSubmit,
}: {
  question: string;
  value: string;
  isSubmitting: boolean;
  detailsHref: string;
  onChange: (value: string) => void;
  onVoiceAnswer: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const canSubmit = value.trim().length > 0 && !isSubmitting;

  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold tracking-tight">
              Waiting for input
            </h2>
            <Badge variant="secondary">Needs input</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            This job is paused until you answer its pending question.
          </p>
        </div>
        <div className="rounded-md border bg-muted/20 p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs font-medium text-muted-foreground">
              Question
            </div>
            <ReadAloudButton text={question} compact />
          </div>
          <p className="mt-2 whitespace-pre-wrap break-words text-base leading-7 text-foreground">
            {question}
          </p>
        </div>
        <form className="space-y-3" onSubmit={onSubmit}>
          <Textarea
            aria-label="Job answer"
            className="min-h-28 resize-y"
            placeholder="Answer..."
            value={value}
            onChange={(event) => onChange(event.target.value)}
            disabled={isSubmitting}
          />
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="outline" asChild>
              <Link href={detailsHref}>
                <Eye className="h-4 w-4" />
                Details
              </Link>
            </Button>
            <VoiceAnswerButton
              disabled={isSubmitting}
              onTranscript={onVoiceAnswer}
            />
            <Button type="submit" disabled={!canSubmit}>
              {isSubmitting ? (
                <Spinner className="size-4" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Submit answer
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function JobThreadPage({ jobId }: JobThreadPageProps) {
  const enableInspector =
    process.env.NEXT_PUBLIC_ENABLE_COPILOT_INSPECTOR === 'true';
  const [thread, setThread] = useState<JobThreadRecord | null>(null);
  const [runs, setRuns] = useState<JobRunRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [isReplying, setIsReplying] = useState(false);
  const voiceTurnWasPendingRef = useRef(false);
  const pendingReplyRef = useRef<{
    message: string;
    clientReplyId: string;
  } | null>(null);

  const load = useCallback(
    async ({ silent = false }: LoadOptions = {}) => {
      if (!silent) {
        setIsLoading(true);
      }
      setLoadError(null);
      try {
        const [threadRecord, runRecords] = await Promise.all([
          fetchJobThread(jobId),
          fetchJobRuns(jobId),
        ]);
        setThread(threadRecord);
        setRuns(runRecords);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Failed to load job thread';
        setLoadError(message);
        if (!silent) {
          toast.error(message);
        }
      } finally {
        if (!silent) {
          setIsLoading(false);
        }
      }
    },
    [jobId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  // Live refresh when this job emits a run event.
  useJobEvents(
    useCallback(
      (incoming: JobRecord) => {
        if (incoming.id === jobId) {
          void load({ silent: true });
        }
      },
      [jobId, load],
    ),
  );

  const job = thread?.job ?? null;
  const threadId = thread?.id ?? job?.job_thread_id ?? jobId;
  const mediaSession = useMediaIngressSession(threadId);
  const showLiveMode = mediaSession.state !== 'idle';
  const status = useMemo(
    () => (job ? getJobStatus(job, new Date()) : null),
    [job],
  );
  const hasJobThread = job ? supportsJobThread(job) : false;
  const isWaiting = job ? supportsJobReply(job) : false;
  const messages = useMemo(() => normalizeMessages(thread), [thread]);
  const events = thread?.events ?? [];

  useEffect(() => {
    if (mediaSession.isAssistantResponsePending) {
      voiceTurnWasPendingRef.current = true;
      return;
    }

    if (voiceTurnWasPendingRef.current) {
      voiceTurnWasPendingRef.current = false;
      void load({ silent: true });
    }
  }, [load, mediaSession.isAssistantResponsePending]);

  useEffect(() => {
    if (mediaSession.state === 'idle' || mediaSession.state === 'error') {
      return;
    }

    const interval = window.setInterval(() => {
      void load({ silent: true });
    }, 2500);
    return () => window.clearInterval(interval);
  }, [load, mediaSession.state]);

  useEffect(() => {
    if (!isWaiting) {
      setInputValue('');
      pendingReplyRef.current = null;
    }
  }, [isWaiting]);

  const submitReply = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const message = inputValue.trim();
      if (!message) return;
      if (!isWaiting) {
        toast.error('This job is not waiting for input.');
        return;
      }
      let pendingReply = pendingReplyRef.current;
      if (!pendingReply || pendingReply.message !== message) {
        pendingReply = {
          message,
          clientReplyId: createClientReplyId(),
        };
        pendingReplyRef.current = pendingReply;
      }

      setIsReplying(true);
      try {
        await replyToJob(jobId, message, pendingReply.clientReplyId);
        toast.success('Answer submitted.');
        pendingReplyRef.current = null;
        setInputValue('');
        await load();
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to submit answer',
        );
      } finally {
        setIsReplying(false);
      }
    },
    [inputValue, isWaiting, jobId, load],
  );

  const handleVoiceAnswer = useCallback((message: string) => {
    setInputValue((current) => {
      const currentText = current.trim();
      return currentText ? `${currentText} ${message}` : message;
    });
  }, []);

  const chatInput = useMemo(
    () => ({
      children: () => {
        return (
          <div className="mx-auto w-full max-w-3xl px-4 pb-4">
            <div className="flex flex-col gap-3 rounded-lg border border-dashed border-border bg-muted/20 px-4 py-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                {isWaiting ? (
                  <>
                    <div className="font-medium text-foreground">
                      {job?.waiting_question ||
                        'The job is waiting for a reply.'}
                    </div>
                    <div>Answer this question from the job detail page.</div>
                  </>
                ) : (
                  <div>Transcript view</div>
                )}
              </div>
              {isWaiting ? (
                <Button size="sm" asChild>
                  <Link href={`/jobs/${jobId}`}>
                    <MessageSquareReply className="h-4 w-4" />
                    Answer
                  </Link>
                </Button>
              ) : null}
            </div>
          </div>
        );
      },
    }),
    [isWaiting, job?.waiting_question, jobId],
  );

  return (
    <div className="flex min-h-[calc(100dvh-8rem)] flex-col gap-5">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold tracking-tight">
              {job?.name || 'Job thread'}
            </h1>
            <p className="break-all font-mono text-xs text-muted-foreground">
              {threadId}
            </p>
          </div>
          {job ? (
            <div className="flex flex-wrap items-center gap-2">
              {status ? (
                <Badge variant={getStatusBadgeVariant(status)}>
                  {getStatusLabel(status)}
                </Badge>
              ) : null}
              <Badge variant="outline">{getScheduleLabel(job)}</Badge>
              <Badge variant="outline">{runs.length} runs</Badge>
              {hasJobThread ? (
                <Badge variant="outline">
                  {events.length || messages.length}{' '}
                  {events.length ? 'events' : 'messages'}
                </Badge>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" asChild>
            <Link href={`/jobs/${jobId}`}>
              <Eye className="h-4 w-4" />
              Details
            </Link>
          </Button>
          <Button
            variant="outline"
            onClick={() => void load()}
            disabled={isLoading || isReplying}
          >
            <RefreshCw
              className={isLoading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
            />
            Refresh
          </Button>
        </div>
      </section>

      {isLoading && !thread ? (
        <Card className="rounded-md border-border/70">
          <CardContent className="flex min-h-56 items-center justify-center">
            <Spinner className="size-6 text-primary" />
          </CardContent>
        </Card>
      ) : null}

      {loadError && !thread ? (
        <Alert variant="destructive">
          <AlertTitle>Unable to load job thread</AlertTitle>
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      ) : null}

      {job && !hasJobThread ? (
        <Alert>
          <AlertTitle>No chat thread for this job type</AlertTitle>
          <AlertDescription>
            This job records runs, but it does not support conversational
            replies.
          </AlertDescription>
        </Alert>
      ) : null}

      {job && hasJobThread ? (
        <>
          {isWaiting ? (
            <div className="space-y-5">
              <WaitingReplyCard
                question={
                  job.waiting_question || 'The job is waiting for a reply.'
                }
                value={inputValue}
                isSubmitting={isReplying}
                detailsHref={`/jobs/${jobId}`}
                onChange={setInputValue}
                onVoiceAnswer={handleVoiceAnswer}
                onSubmit={submitReply}
              />
              {events.length ? <JobEventTimeline events={events} /> : null}
            </div>
          ) : showLiveMode ? (
            <div className="min-h-[34rem] flex-1 overflow-hidden rounded-md border border-border/70 bg-background shadow-sm shadow-black/5">
              <LiveModePanel artifacts={[]} session={mediaSession} />
            </div>
          ) : events.length ? (
            <JobEventTimeline events={events} />
          ) : (
            <div className="min-h-[34rem] flex-1 overflow-hidden rounded-md border border-border/70 bg-background shadow-sm shadow-black/5">
              <CopilotKitProvider
                runtimeUrl="/api/copilotkit"
                showDevConsole={enableInspector}
                renderToolCalls={chatToolCallRenderers}
              >
                <CopilotChatConfigurationProvider
                  agentId="copilot"
                  threadId={threadId}
                  labels={{
                    chatInputPlaceholder: 'Transcript view',
                  }}
                >
                  <CopilotChatView
                    autoScroll
                    className="smart-living-copilot-chat h-full"
                    input={chatInput}
                    messageView={MessageViewWithWotSummary}
                    messages={messages}
                    welcomeScreen={false}
                  />
                </CopilotChatConfigurationProvider>
              </CopilotKitProvider>
            </div>
          )}
        </>
      ) : null}

      {job ? (
        <JobRunHistoryCard
          runs={runs}
          description="Execution attempts connected to this checkpoint thread."
          outcome={runOutcome}
          readOutcome
        />
      ) : null}
    </div>
  );
}
