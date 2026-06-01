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
  type ReactElement,
} from 'react';
import Link from 'next/link';
import { Eye, Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

import { JobRunHistoryCard } from '@/components/jobs/job-run-history';
import { LiveModePanel } from '@/components/copilot/live-mode-panel';
import { MediaIngressControl } from '@/components/copilot/media-ingress-control';
import { chatToolCallRenderers } from '@/components/copilot/chat-tool-call-renderer';
import { MessageViewWithWotSummary } from '@/components/copilot/wot-interaction-summary';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useJobEvents } from '@/hooks/use-job-events';
import { useMediaIngressSession } from '@/hooks/use-media-ingress-session';
import {
  getJobStatus,
  getScheduleLabel,
  getStatusBadgeVariant,
  getStatusLabel,
  supportsJobReply,
  supportsJobThread,
} from '@/lib/job-formatters';
import {
  type JobRecord,
  type JobRunRecord,
  type JobThreadRecord,
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

type ChatInputChildren = {
  textArea: ReactElement;
  sendButton: ReactElement;
  disclaimer: ReactElement;
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
  if (run.error?.trim()) return run.error.trim();
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

  const submitReply = useCallback(
    async (value: string) => {
      const message = value.trim();
      if (!message) return;
      if (!isWaiting) {
        toast.error('This job is not waiting for input.');
        return;
      }

      setIsReplying(true);
      try {
        await replyToJob(jobId, message);
        toast.success('Reply submitted.');
        setInputValue('');
        await load();
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to submit reply',
        );
      } finally {
        setIsReplying(false);
      }
    },
    [isWaiting, jobId, load],
  );

  const chatInput = useMemo(
    () => ({
      children: ({ textArea, sendButton, disclaimer }: ChatInputChildren) => {
        if (!isWaiting) {
          return (
            <div className="mx-auto w-full max-w-3xl px-4 pb-4">
              <div className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
                This job is not waiting for input.
              </div>
            </div>
          );
        }

        return (
          <div className="mx-auto w-full max-w-3xl px-4 pb-4">
            <div className="rounded-lg border border-border bg-background px-3 py-2 shadow-sm">
              <div className="min-h-16">{textArea}</div>
              <div className="flex items-center justify-between gap-2 border-t border-border pt-2">
                <MediaIngressControl session={mediaSession} />
                {sendButton}
              </div>
            </div>
            {disclaimer}
          </div>
        );
      },
    }),
    [isWaiting, mediaSession],
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
                <Badge variant="outline">{messages.length} messages</Badge>
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
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
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
            <Alert>
              <AlertTitle>Waiting for input</AlertTitle>
              <AlertDescription>
                {job.waiting_question || 'The job is waiting for a reply.'}
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="min-h-[34rem] flex-1 overflow-hidden rounded-md border border-border/70 bg-background shadow-sm shadow-black/5">
            {showLiveMode ? (
              <LiveModePanel artifacts={[]} session={mediaSession} />
            ) : (
              <CopilotKitProvider
                runtimeUrl="/api/copilotkit"
                showDevConsole={enableInspector}
                renderToolCalls={chatToolCallRenderers}
              >
                <CopilotChatConfigurationProvider
                  agentId="copilot"
                  threadId={threadId}
                  labels={{
                    chatInputPlaceholder: isWaiting
                      ? 'Answer this job...'
                      : 'Job is not waiting for input',
                  }}
                >
                  <CopilotChatView
                    autoScroll
                    className="smart-living-copilot-chat h-full"
                    input={chatInput}
                    inputValue={inputValue}
                    isRunning={isReplying}
                    messageView={MessageViewWithWotSummary}
                    messages={messages}
                    onInputChange={setInputValue}
                    onSubmitMessage={isWaiting ? submitReply : undefined}
                    welcomeScreen={false}
                  />
                </CopilotChatConfigurationProvider>
              </CopilotKitProvider>
            )}
          </div>
        </>
      ) : null}

      {job ? (
        <JobRunHistoryCard
          runs={runs}
          description="Execution attempts connected to this checkpoint thread."
          outcome={runOutcome}
        />
      ) : null}
    </div>
  );
}
