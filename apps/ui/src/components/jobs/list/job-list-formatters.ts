import {
  formatInterval,
  formatRelativeTime,
  getJobStatus,
} from '@/lib/job-formatters';
import { type JobRecord } from '@/lib/jobs-api';

export type JobTabValue =
  | 'all'
  | 'active'
  | 'waiting'
  | 'failed'
  | 'time'
  | 'event'
  | 'disabled';

export const JOB_TABS: { value: JobTabValue; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'waiting', label: 'Needs input' },
  { value: 'failed', label: 'Failed' },
  { value: 'time', label: 'Time' },
  { value: 'event', label: 'Events' },
  { value: 'disabled', label: 'Paused' },
];

export type JobTabCounts = Record<JobTabValue, number>;

export function getJobSearchableText(job: JobRecord): string {
  return [
    job.name,
    job.id,
    job.job_thread_id,
    job.action_kind,
    job.interaction_mode,
    job.output_kind,
    job.trigger_kind,
    job.schedule_kind,
    job.cron_expression,
    job.cron_timezone,
    job.thing_id,
    job.event_name,
    job.last_error,
    job.last_response,
    job.last_run_status,
    job.waiting_question,
    job.virtual_thing_id,
    job.prompt,
    job.analysis_code,
    job.record_schema ? JSON.stringify(job.record_schema) : null,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

export function renderRelative(
  value: string | null,
  hydrated: boolean,
  now: Date,
): string {
  return hydrated ? formatRelativeTime(value, now) : (value ?? 'Not available');
}

export function actionLabel(job: JobRecord): string {
  if (job.output_kind === 'structured_record') return 'Record prompt';
  return job.action_kind === 'analysis' ? 'Analysis' : 'Prompt';
}

export function triggerLabel(job: JobRecord): string {
  if (job.trigger_kind === 'event') return job.event_name || 'Event';
  if (job.schedule_kind === 'once') return 'Once';
  if (job.schedule_kind === 'cron' && job.cron_expression) {
    return `Cron ${job.cron_expression}`;
  }
  if (job.interval_seconds) {
    return `Every ${formatInterval(job.interval_seconds)}`;
  }
  return 'Time';
}

export function targetLabel(job: JobRecord): string {
  if (job.trigger_kind === 'event') {
    return job.thing_id || 'Unbound event target';
  }
  return 'Time trigger';
}

export function hasActiveRun(job: JobRecord): boolean {
  return Boolean(job.active_run_id);
}

export function jobMatchesTab(
  tab: JobTabValue,
  job: JobRecord,
  status: ReturnType<typeof getJobStatus>,
): boolean {
  if (tab === 'all') return true;
  if (tab === 'active') return status === 'running' || status === 'queued';
  if (tab === 'waiting') return status === 'waiting_for_input';
  if (tab === 'failed') return status === 'failed';
  if (tab === 'time') return job.trigger_kind === 'time';
  if (tab === 'event') return job.trigger_kind === 'event';
  return status === 'disabled';
}

export function getJobTabCounts(jobs: JobRecord[], now: Date): JobTabCounts {
  const stats = jobs.reduce(
    (acc, job) => {
      const status = getJobStatus(job, now);
      acc.total += 1;
      if (status === 'running' || status === 'queued') acc.active += 1;
      if (status === 'waiting_for_input') acc.waiting += 1;
      if (status === 'failed') acc.failed += 1;
      if (job.trigger_kind === 'time') acc.time += 1;
      if (job.trigger_kind === 'event') acc.event += 1;
      if (status === 'disabled') acc.disabled += 1;
      return acc;
    },
    {
      total: 0,
      active: 0,
      waiting: 0,
      failed: 0,
      time: 0,
      event: 0,
      disabled: 0,
    },
  );

  return {
    all: stats.total,
    active: stats.active,
    waiting: stats.waiting,
    failed: stats.failed,
    time: stats.time,
    event: stats.event,
    disabled: stats.disabled,
  };
}

export function getJobTabLabel(tabValue: JobTabValue): string {
  return JOB_TABS.find((tab) => tab.value === tabValue)?.label ?? 'All';
}
