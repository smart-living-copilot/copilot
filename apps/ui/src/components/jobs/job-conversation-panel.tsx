'use client';

import {
  CopilotChatConfigurationProvider,
  CopilotKitProvider,
  CopilotChatView,
  type Message,
} from '@copilotkit/react-core/v2';
import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Bot,
  CheckCircle2,
  CircleDot,
  ClipboardCheck,
  MessageSquare,
  MessageSquareReply,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';

import { chatToolCallRenderers } from '@/components/copilot/chat-tool-call-renderer';
import { MessageViewWithWotSummary } from '@/components/copilot/wot-interaction-summary';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useJobEvents } from '@/hooks/use-job-events';
import { supportsJobReply } from '@/lib/job-formatters';
import {
  type JobRecord,
  type JobRunEventRecord,
  type JobRunEventType,
  type JobThreadRecord,
  fetchJobThread,
} from '@/lib/jobs-api';

export function normalizeMessages(thread: JobThreadRecord | null): Message[] {
  return (thread?.messages ?? []).map((message, index) => {
    return {
      ...message,
      id: message.id ?? `job-message-${index}`,
    } as Message;
  });
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

export function JobEventTimeline({ events }: { events: JobRunEventRecord[] }) {
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

/** The CopilotKit-rendered message transcript for a job thread. */
export function JobTranscript({
  messages,
  threadId,
  jobId,
  isWaiting,
  waitingQuestion,
}: {
  messages: Message[];
  threadId: string;
  jobId: string;
  isWaiting: boolean;
  waitingQuestion?: string | null;
}) {
  const enableInspector =
    process.env.NEXT_PUBLIC_ENABLE_COPILOT_INSPECTOR === 'true';

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
                      {waitingQuestion || 'The job is waiting for a reply.'}
                    </div>
                    <div>Answer this question from the Overview tab.</div>
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
    [isWaiting, waitingQuestion, jobId],
  );

  return (
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
  );
}

/**
 * Self-contained conversation view for the job detail "Conversation" tab.
 * Loads the job thread, live-refreshes on run events, and shows the message
 * transcript (falling back to the event timeline when there are no messages).
 */
export function JobConversationPanel({
  jobId,
  job,
}: {
  jobId: string;
  job: JobRecord;
}) {
  const [thread, setThread] = useState<JobThreadRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(
    async ({ silent = false }: { silent?: boolean } = {}) => {
      if (!silent) setIsLoading(true);
      setLoadError(null);
      try {
        setThread(await fetchJobThread(jobId));
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : 'Failed to load conversation';
        setLoadError(message);
        if (!silent) toast.error(message);
      } finally {
        if (!silent) setIsLoading(false);
      }
    },
    [jobId],
  );

  useEffect(() => {
    void load();
  }, [load]);

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

  const threadId = thread?.id ?? job.job_thread_id ?? jobId;
  const messages = useMemo(() => normalizeMessages(thread), [thread]);
  const events = thread?.events ?? [];
  const isWaiting = supportsJobReply(job);

  if (isLoading && !thread) {
    return <Skeleton className="h-[34rem] rounded-md" />;
  }

  if (loadError && !thread) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Unable to load conversation</AlertTitle>
        <AlertDescription>{loadError}</AlertDescription>
      </Alert>
    );
  }

  if (messages.length === 0 && events.length === 0) {
    return (
      <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
        <CardContent className="flex min-h-40 items-center justify-center text-sm text-muted-foreground">
          No conversation yet.
        </CardContent>
      </Card>
    );
  }

  if (messages.length === 0) {
    return <JobEventTimeline events={events} />;
  }

  return (
    <JobTranscript
      messages={messages}
      threadId={threadId}
      jobId={jobId}
      isWaiting={isWaiting}
      waitingQuestion={job.waiting_question}
    />
  );
}
