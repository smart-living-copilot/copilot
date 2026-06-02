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

const STATUS_LABELS: Record<string, string> = {
  running: 'Running',
  queued: 'Queued',
  scheduled: 'Scheduled',
  succeeded: 'Succeeded',
  failed: 'Failed',
  skipped: 'Skipped',
  cancelled: 'Cancelled',
  disabled: 'Paused',
  waiting_for_input: 'Needs input',
  'waiting-event': 'Waiting for event',
};

/** Human-readable label for a job or run status enum value. */
export function getStatusLabel(status: JobDisplayStatus | string): string {
  return STATUS_LABELS[status] ?? status.replace(/[_-]/g, ' ');
}

/** Humanize an interval in seconds, e.g. 300 -> "5 min", 5400 -> "1 hr 30 min". */
export function formatInterval(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return `${seconds}s`;
  }
  if (seconds < 60) {
    return `${seconds} sec`;
  }

  const units: [label: string, size: number][] = [
    ['day', 86400],
    ['hr', 3600],
    ['min', 60],
  ];
  const parts: string[] = [];
  let remaining = Math.round(seconds);
  for (const [label, size] of units) {
    const count = Math.floor(remaining / size);
    if (count > 0) {
      parts.push(`${count} ${label}`);
      remaining -= count * size;
    }
  }
  return parts.slice(0, 2).join(' ');
}

const RELATIVE_THRESHOLDS: [
  limit: number,
  divisor: number,
  unit: Intl.RelativeTimeFormatUnit,
][] = [
  [60, 1, 'second'],
  [3600, 60, 'minute'],
  [86400, 3600, 'hour'],
  [604800, 86400, 'day'],
];

/**
 * Relative time like "2 min ago" / "in 5 min", falling back to an absolute
 * date for anything older than a week. Pass `now` from a hydrated context to
 * avoid SSR mismatches.
 */
export function formatRelativeTime(
  value: string | null,
  now: Date = new Date(),
): string {
  if (!value) {
    return 'Not available';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  const diffSeconds = (date.getTime() - now.getTime()) / 1000;
  const abs = Math.abs(diffSeconds);
  if (abs < 10) {
    return 'just now';
  }
  if (abs >= 604800) {
    return formatDateTime(value);
  }

  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  for (const [limit, divisor, unit] of RELATIVE_THRESHOLDS) {
    if (abs < limit) {
      return formatter.format(Math.round(diffSeconds / divisor), unit);
    }
  }
  return formatDateTime(value);
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
    return `Every ${formatInterval(job.interval_seconds)}`;
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
  job: Pick<JobRecord, 'action_kind' | 'last_run_status' | 'waiting_question'>,
): boolean {
  return (
    supportsJobThread(job) &&
    (job.last_run_status === 'waiting_for_input' ||
      Boolean(job.waiting_question?.trim()))
  );
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
