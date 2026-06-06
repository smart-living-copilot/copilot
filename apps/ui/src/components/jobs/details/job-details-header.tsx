'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Ban,
  Pause,
  Pencil,
  Play,
  Power,
  RefreshCw,
  Trash2,
} from 'lucide-react';

import { ConfirmDialog } from '@/components/confirm-dialog';
import { PulseDot } from '@/components/jobs/details/pulse-dot';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import {
  getScheduleLabel,
  getStatusBadgeVariant,
  getStatusLabel,
  type JobDisplayStatus,
} from '@/lib/job-formatters';
import { type JobRecord } from '@/lib/jobs-api';
import { withReturnTo } from '@/lib/return-to';

interface JobDetailsHeaderProps {
  jobId: string;
  job: JobRecord | null;
  status: JobDisplayStatus | null;
  isLoading: boolean;
  isRunning: boolean;
  isDeleting: boolean;
  isBusy: boolean;
  onRefresh: () => void;
  onRun: () => void;
  onCancel: () => void;
  onToggleEnabled: () => void;
  onDelete: () => void | Promise<void>;
}

export function JobDetailsHeader({
  jobId,
  job,
  status,
  isLoading,
  isRunning,
  isDeleting,
  isBusy,
  onRefresh,
  onRun,
  onCancel,
  onToggleEnabled,
  onDelete,
}: JobDetailsHeaderProps) {
  const disabled = isLoading || isRunning || isDeleting || isBusy;
  const pathname = usePathname();
  const editHref = withReturnTo(`/jobs/${jobId}/edit`, pathname);

  return (
    <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="space-y-2">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">
            {job?.name || 'Job details'}
          </h1>
          <p className="break-all font-mono text-xs text-muted-foreground">
            {jobId}
          </p>
        </div>
        {job ? (
          <div className="flex flex-wrap items-center gap-2">
            {status ? (
              <Badge variant={getStatusBadgeVariant(status)}>
                {status === 'waiting_for_input' ? (
                  <PulseDot className="mr-1.5" />
                ) : null}
                {getStatusLabel(status)}
              </Badge>
            ) : null}
            <Badge variant="outline">{getStatusLabel(job.action.kind)}</Badge>
            <Badge variant="outline">{getScheduleLabel(job)}</Badge>
          </div>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={onRefresh} disabled={disabled}>
          <RefreshCw
            className={isLoading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
          />
          Refresh
        </Button>
        {job ? (
          <Button variant="outline" asChild>
            <Link href={editHref}>
              <Pencil className="h-4 w-4" />
              Edit
            </Link>
          </Button>
        ) : null}
        {job?.active_run_id ? (
          <Button variant="outline" onClick={onCancel} disabled={disabled}>
            <Ban className="h-4 w-4" />
            Cancel run
          </Button>
        ) : null}
        {job ? (
          <Button
            variant="outline"
            onClick={onToggleEnabled}
            disabled={disabled}
          >
            {job.enabled ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Power className="h-4 w-4" />
            )}
            {job.enabled ? 'Pause' : 'Resume'}
          </Button>
        ) : null}
        <Button
          onClick={onRun}
          disabled={!job || disabled || Boolean(job.active_run_id)}
        >
          {isRunning ? (
            <Spinner className="size-4" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          Run
        </Button>
        <ConfirmDialog
          title={job ? `Delete "${job.name}"?` : 'Delete job?'}
          description="This permanently removes the job, its schedule, and its run history. This cannot be undone."
          confirmLabel="Delete"
          destructive
          onConfirm={onDelete}
          trigger={
            <Button variant="destructive" disabled={!job || disabled}>
              {isDeleting ? (
                <Spinner className="size-4" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Delete
            </Button>
          }
        />
      </div>
    </section>
  );
}
