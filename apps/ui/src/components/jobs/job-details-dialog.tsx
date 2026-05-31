'use client';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { type JobRecord } from '@/lib/jobs-api';

function formatDateTime(value: string | null): string {
  if (!value) return 'Not available';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function getJobStatus(job: JobRecord, now: Date): string {
  if (!job.enabled) return 'disabled';
  if (job.trigger_kind === 'event') return 'waiting-event';
  if (!job.next_run_at) return 'queued';
  const nextRunAt = new Date(job.next_run_at);
  if (Number.isNaN(nextRunAt.getTime()) || nextRunAt <= now) return 'queued';
  return 'scheduled';
}

function getScheduleLabel(job: JobRecord): string {
  if (job.trigger_kind === 'event') {
    return job.event_name
      ? `On event: ${job.event_name}`
      : 'On subscribed event';
  }
  if (job.interval_seconds) return `Every ${job.interval_seconds}s`;
  if (job.run_at) return `Once at ${formatDateTime(job.run_at)}`;
  return 'Manual or pending schedule';
}

function formatJson(value: unknown): string {
  if (value == null) return 'Not available';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

interface JobDetailsDialogProps {
  job: JobRecord | null;
  onOpenChange: (open: boolean) => void;
}

export function JobDetailsDialog({ job, onOpenChange }: JobDetailsDialogProps) {
  const purposeLabel =
    job?.action_kind === 'analysis'
      ? {
          label: 'Analysis code',
          content: job.analysis_code?.trim() || '(empty analysis code)',
        }
      : { label: 'Prompt', content: job?.prompt?.trim() || '(empty prompt)' };

  return (
    <Dialog open={job !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[94vh] w-[99vw] sm:w-[98vw] lg:w-[96vw] 2xl:w-[94vw] !max-w-[99vw] sm:!max-w-[98vw] lg:!max-w-[96vw] 2xl:!max-w-[94vw] overflow-y-auto">
        {job ? (
          <>
            <DialogHeader>
              <DialogTitle>{job.name}</DialogTitle>
              <DialogDescription>
                Full execution detail for {job.id}
              </DialogDescription>
            </DialogHeader>

            <div className="grid gap-4">
              <div className="grid gap-4 md:grid-cols-2">
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Identity</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div>
                      <span className="font-medium">Created from thread:</span>{' '}
                      {job.created_from_thread_id}
                    </div>
                    <div>
                      <span className="font-medium">Job thread:</span>{' '}
                      {job.job_thread_id}
                    </div>
                    <div>
                      <span className="font-medium">Action:</span>{' '}
                      {job.action_kind}
                    </div>
                    <div>
                      <span className="font-medium">Trigger:</span>{' '}
                      {job.trigger_kind}
                    </div>
                    <div>
                      <span className="font-medium">Status:</span>{' '}
                      {getJobStatus(job, new Date())}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Timing</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div>
                      <span className="font-medium">Schedule:</span>{' '}
                      {getScheduleLabel(job)}
                    </div>
                    <div>
                      <span className="font-medium">Next run:</span>{' '}
                      {formatDateTime(job.next_run_at)}
                    </div>
                    <div>
                      <span className="font-medium">Last run:</span>{' '}
                      {formatDateTime(job.last_run_at)}
                    </div>
                    <div>
                      <span className="font-medium">Created:</span>{' '}
                      {formatDateTime(job.created_at)}
                    </div>
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Purpose</CardTitle>
                  <CardDescription>{purposeLabel.label}</CardDescription>
                </CardHeader>
                <CardContent>
                  <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg border bg-muted/30 p-4 text-xs text-muted-foreground">
                    {purposeLabel.content}
                  </pre>
                </CardContent>
              </Card>

              <div className="grid gap-4 md:grid-cols-2">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Target</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div>
                      <span className="font-medium">Thing ID:</span>{' '}
                      {job.thing_id || 'Not set'}
                    </div>
                    <div>
                      <span className="font-medium">Event name:</span>{' '}
                      {job.event_name || 'Not set'}
                    </div>
                    <div>
                      <span className="font-medium">Subscription ID:</span>{' '}
                      {job.subscription_id || 'Not set'}
                    </div>
                    <div>
                      <span className="font-medium">Run count:</span>{' '}
                      {job.run_count}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Diagnostics</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div>
                      <span className="font-medium">Last fetch value:</span>{' '}
                      {job.last_fetch_value || 'Not captured'}
                    </div>
                    <div>
                      <span className="font-medium">Last error:</span>{' '}
                      {job.last_error || 'No recent error'}
                    </div>
                    <div>
                      <span className="font-medium">Updated:</span>{' '}
                      {formatDateTime(job.updated_at)}
                    </div>
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Last Result</CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg border bg-muted/30 p-4 text-xs text-muted-foreground">
                    {job.last_response || 'No result captured yet.'}
                  </pre>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">
                    Subscription Input
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg border bg-muted/30 p-4 text-xs text-muted-foreground">
                    {formatJson(job.subscription_input)}
                  </pre>
                </CardContent>
              </Card>
            </div>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
