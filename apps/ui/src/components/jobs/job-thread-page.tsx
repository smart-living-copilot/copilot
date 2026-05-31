'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Loader2,
  MessageSquareReply,
  RefreshCw,
  Send,
} from 'lucide-react';
import { toast } from 'sonner';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import {
  formatDateTime,
  getJobStatus,
  getScheduleLabel,
  getStatusBadgeVariant,
} from '@/lib/job-formatters';
import {
  type JobRunRecord,
  type JobThreadMessage,
  type JobThreadRecord,
  fetchJobRuns,
  fetchJobThread,
  replyToJob,
} from '@/lib/jobs-api';

interface JobThreadPageProps {
  jobId: string;
}

function formatMessageContent(content: unknown): string {
  if (content == null) return '';
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object' && 'text' in item) {
          const text = (item as { text?: unknown }).text;
          return typeof text === 'string' ? text : JSON.stringify(text);
        }
        return JSON.stringify(item);
      })
      .filter(Boolean)
      .join('');
  }
  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return String(content);
  }
}

function messageRole(message: JobThreadMessage): string {
  return message.role || message.type || message.name || 'message';
}

export function JobThreadPage({ jobId }: JobThreadPageProps) {
  const [thread, setThread] = useState<JobThreadRecord | null>(null);
  const [runs, setRuns] = useState<JobRunRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [reply, setReply] = useState('');
  const [isReplying, setIsReplying] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      const [threadRecord, runRecords] = await Promise.all([
        fetchJobThread(jobId),
        fetchJobRuns(jobId),
      ]);
      setThread(threadRecord);
      setRuns(runRecords);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to load job thread',
      );
    } finally {
      setIsLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void load();
  }, [load]);

  const job = thread?.job ?? null;
  const status = useMemo(
    () => (job ? getJobStatus(job, new Date()) : null),
    [job],
  );
  const isWaiting = job?.last_run_status === 'waiting_for_input';

  const submitReply = useCallback(async () => {
    const message = reply.trim();
    if (!message) return;
    setIsReplying(true);
    try {
      await replyToJob(jobId, message);
      toast.success('Reply submitted.');
      setReply('');
      await load();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to submit reply',
      );
    } finally {
      setIsReplying(false);
    }
  }, [jobId, load, reply]);

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-3">
          <Button variant="outline" size="sm" asChild>
            <Link href="/jobs">
              <ArrowLeft className="h-3.5 w-3.5" />
              Jobs
            </Link>
          </Button>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">
              {job?.name || 'Job thread'}
            </h1>
            <p className="mt-1 font-mono text-xs text-muted-foreground">
              {jobId}
            </p>
          </div>
        </div>
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
      </section>

      {isLoading && !thread ? (
        <div className="flex min-h-56 items-center justify-center rounded-md border">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : null}

      {job ? (
        <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-4">
            {isWaiting ? (
              <Alert>
                <MessageSquareReply className="h-4 w-4" />
                <AlertTitle>Waiting for input</AlertTitle>
                <AlertDescription>
                  {job.waiting_question || 'The job is waiting for a reply.'}
                </AlertDescription>
              </Alert>
            ) : null}

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Hidden Thread</CardTitle>
                <CardDescription>{thread?.id}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {thread?.messages.length ? (
                  thread.messages.map((message, index) => (
                    <div
                      key={message.id || index}
                      className="rounded-md border bg-muted/20 p-3"
                    >
                      <div className="mb-2 flex items-center gap-2">
                        <Badge variant="outline">{messageRole(message)}</Badge>
                      </div>
                      <pre className="whitespace-pre-wrap break-words text-sm text-muted-foreground">
                        {formatMessageContent(message.content)}
                      </pre>
                    </div>
                  ))
                ) : (
                  <div className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
                    No checkpointed messages yet.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <aside className="space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Job</CardTitle>
                <CardDescription>{getScheduleLabel(job)}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {status ? (
                  <Badge variant={getStatusBadgeVariant(status)}>
                    {status}
                  </Badge>
                ) : null}
                <div>
                  <span className="font-medium">Last run:</span>{' '}
                  {job.last_run_status || 'none'}
                </div>
                <div>
                  <span className="font-medium">Active run:</span>{' '}
                  {job.active_run_id || 'none'}
                </div>
                <div>
                  <span className="font-medium">Updated:</span>{' '}
                  {formatDateTime(job.updated_at)}
                </div>
              </CardContent>
            </Card>

            {isWaiting ? (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Reply</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Textarea
                    value={reply}
                    onChange={(event) => setReply(event.target.value)}
                    rows={5}
                    placeholder="Send the missing input for this job"
                  />
                  <Button
                    className="w-full"
                    onClick={() => void submitReply()}
                    disabled={isReplying || !reply.trim()}
                  >
                    {isReplying ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                    Submit reply
                  </Button>
                </CardContent>
              </Card>
            ) : null}

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Run History</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Status</TableHead>
                        <TableHead>Source</TableHead>
                        <TableHead>Started</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {runs.map((run) => (
                        <TableRow key={run.id}>
                          <TableCell>
                            <Badge variant={getStatusBadgeVariant(run.status)}>
                              {run.status}
                            </Badge>
                          </TableCell>
                          <TableCell>{run.source}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {formatDateTime(run.started_at)}
                          </TableCell>
                        </TableRow>
                      ))}
                      {!runs.length ? (
                        <TableRow>
                          <TableCell
                            colSpan={3}
                            className="text-sm text-muted-foreground"
                          >
                            No runs recorded yet.
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </aside>
        </section>
      ) : null}
    </div>
  );
}
