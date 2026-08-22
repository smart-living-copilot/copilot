'use client';

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react';
import { toast } from 'sonner';

import {
  JobTranscript,
  normalizeMessages,
} from '@/components/jobs/job-conversation-panel';
import { JobEventTimeline } from '@/components/jobs/job-event-timeline';
import { JobRunHistoryCard } from '@/components/jobs/job-run-history';
import { JobThreadHeader } from '@/components/jobs/thread/job-thread-header';
import { WaitingReplyCard } from '@/components/jobs/thread/waiting-reply-card';
import { LiveModePanel } from '@/components/wotbot/live-mode-panel';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Card, CardContent } from '@/components/ui/card';
import { Spinner } from '@/components/ui/spinner';
import { useJobEvents } from '@/hooks/use-job-events';
import { useMediaIngressSession } from '@/hooks/use-media-ingress-session';
import { supportsJobReply, supportsJobThread } from '@/lib/job-formatters';
import { formatJobRunOutcome } from '@/lib/job-run-output';
import {
  type JobRecord,
  type JobRunPage,
  type JobRunRecord,
  type JobThreadRecord,
  createClientReplyId,
  fetchJobRunsPage,
  fetchJobThread,
  replyToJob,
} from '@/lib/jobs-api';

interface JobThreadPageProps {
  jobId: string;
}

type LoadOptions = {
  silent?: boolean;
  runOffset?: number;
};

const RUN_HISTORY_PAGE_SIZE = 5;

export function JobThreadPage({ jobId }: JobThreadPageProps) {
  const [thread, setThread] = useState<JobThreadRecord | null>(null);
  const [runs, setRuns] = useState<JobRunRecord[]>([]);
  const [runPage, setRunPage] = useState<JobRunPage>({
    runs: [],
    total: 0,
    limit: RUN_HISTORY_PAGE_SIZE,
    offset: 0,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [isReplying, setIsReplying] = useState(false);
  const voiceTurnWasPendingRef = useRef(false);
  const pendingReplyRef = useRef<{
    message: string;
    clientReplyId: string;
  } | null>(null);
  const runOffsetRef = useRef(0);

  const load = useCallback(
    async ({
      silent = false,
      runOffset = runOffsetRef.current,
    }: LoadOptions = {}) => {
      if (!silent) {
        setIsLoading(true);
      }
      setLoadError(null);
      try {
        const [threadRecord, runRecords] = await Promise.all([
          fetchJobThread(jobId),
          fetchJobRunsPage(jobId, {
            limit: RUN_HISTORY_PAGE_SIZE,
            offset: runOffset,
          }),
        ]);
        setThread(threadRecord);
        setRuns(runRecords.runs);
        setRunPage(runRecords);
        runOffsetRef.current = runRecords.offset;
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

  const handleRunPageChange = useCallback(
    (offset: number) => {
      const nextOffset = Math.max(0, offset);
      runOffsetRef.current = nextOffset;
      void load({ silent: true, runOffset: nextOffset });
    },
    [load],
  );

  return (
    <div className="flex min-h-[calc(100dvh-8rem)] flex-col gap-5">
      <JobThreadHeader
        jobId={jobId}
        threadId={threadId}
        job={job}
        runsCount={runPage.total}
        eventsCount={events.length}
        messagesCount={messages.length}
        hasJobThread={hasJobThread}
        isLoading={isLoading}
        isReplying={isReplying}
        onRefresh={() => void load()}
      />

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
            <JobTranscript
              messages={messages}
              jobId={jobId}
              isWaiting={isWaiting}
              waitingQuestion={job.waiting_question}
            />
          )}
        </>
      ) : null}

      {job ? (
        <JobRunHistoryCard
          runs={runs}
          totalRuns={runPage.total}
          limit={runPage.limit}
          offset={runPage.offset}
          description="Execution attempts connected to this checkpoint thread."
          outcome={formatJobRunOutcome}
          onPageChange={handleRunPageChange}
        />
      ) : null}
    </div>
  );
}
