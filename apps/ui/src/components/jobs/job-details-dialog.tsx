'use client';

import Link from 'next/link';
import { MessagesSquare } from 'lucide-react';

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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  formatDateTime,
  getJobStatus,
  getPurposePreview,
  getScheduleLabel,
  getStatusBadgeVariant,
} from '@/lib/job-formatters';
import { type JobRecord } from '@/lib/jobs-api';

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
  const purposeLabel = job
    ? getPurposePreview(job)
    : { label: 'Prompt', content: '(empty prompt)' };
  const status = job ? getJobStatus(job, new Date()) : null;

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
            <div className="flex flex-wrap items-center gap-2">
              {status ? (
                <Badge variant={getStatusBadgeVariant(status)}>{status}</Badge>
              ) : null}
              {job.last_run_status ? (
                <Badge variant="outline">last run {job.last_run_status}</Badge>
              ) : null}
              <Button size="sm" variant="outline" asChild>
                <Link href={`/jobs/${job.id}/thread`}>
                  <MessagesSquare className="h-3.5 w-3.5" />
                  Open job thread
                </Link>
              </Button>
            </div>

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
                      <span className="font-medium">Status:</span> {status}
                    </div>
                    <div>
                      <span className="font-medium">Active run:</span>{' '}
                      {job.active_run_id || 'None'}
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
                      <span className="font-medium">Active since:</span>{' '}
                      {formatDateTime(job.active_run_started_at)}
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
                      <span className="font-medium">Last error:</span>{' '}
                      {job.last_error || 'No recent error'}
                    </div>
                    <div>
                      <span className="font-medium">Waiting question:</span>{' '}
                      {job.waiting_question || 'Not waiting'}
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
