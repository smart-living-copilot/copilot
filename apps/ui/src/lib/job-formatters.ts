import { type JobRecord } from '@/lib/jobs-api';

export type JobDisplayStatus =
  | 'running'
  | 'waiting_for_input'
  | 'skipped'
  | 'failed'
  | 'succeeded'
  | 'disabled'
  | 'waiting-event'
  | 'queued'
  | 'scheduled';

export function formatDateTime(value: string | null): string {
  if (!value) {
    return 'Not available';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

export function getJobStatus(job: JobRecord, now: Date): JobDisplayStatus {
  if (job.last_run_status === 'running') return 'running';
  if (job.last_run_status === 'waiting_for_input') return 'waiting_for_input';
  if (job.last_run_status === 'skipped') return 'skipped';
  if (job.last_run_status === 'failed') return 'failed';
  if (!job.enabled) return 'disabled';
  if (job.trigger_kind === 'event') return 'waiting-event';
  if (!job.next_run_at)
    return job.last_run_status === 'succeeded' ? 'succeeded' : 'queued';

  const nextRunAt = new Date(job.next_run_at);
  if (Number.isNaN(nextRunAt.getTime()) || nextRunAt <= now) {
    return 'queued';
  }
  return 'scheduled';
}

export function getScheduleLabel(job: JobRecord): string {
  if (job.trigger_kind === 'event') {
    return job.event_name
      ? `On event: ${job.event_name}`
      : 'On subscribed event';
  }
  if (job.interval_seconds) {
    return `Every ${job.interval_seconds}s`;
  }
  if (job.run_at) {
    return `Once at ${formatDateTime(job.run_at)}`;
  }
  return 'Manual or pending schedule';
}

export function getPurposePreview(job: JobRecord): {
  label: string;
  content: string;
} {
  if (job.action_kind === 'analysis') {
    return {
      label: 'Analysis code',
      content: job.analysis_code?.trim() || '(empty analysis code)',
    };
  }

  return {
    label: 'Prompt',
    content: job.prompt?.trim() || '(empty prompt)',
  };
}

export function supportsJobThread(
  job: Pick<JobRecord, 'action_kind'>,
): boolean {
  return job.action_kind === 'prompt';
}

export function supportsJobReply(
  job: Pick<JobRecord, 'action_kind' | 'last_run_status'>,
): boolean {
  return supportsJobThread(job) && job.last_run_status === 'waiting_for_input';
}

export function supportsTimeFields(
  job: Pick<JobRecord, 'trigger_kind'>,
): boolean {
  return job.trigger_kind === 'time';
}

export function supportsEventFields(
  job: Pick<JobRecord, 'trigger_kind'>,
): boolean {
  return job.trigger_kind === 'event';
}

export function getStatusBadgeVariant(
  status: JobDisplayStatus | string,
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'queued' || status === 'running') return 'default';
  if (
    status === 'waiting-event' ||
    status === 'scheduled' ||
    status === 'waiting_for_input' ||
    status === 'succeeded'
  ) {
    return 'secondary';
  }
  if (status === 'failed') return 'destructive';
  if (status === 'disabled' || status === 'skipped') return 'outline';
  return 'outline';
}
