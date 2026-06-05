import {
  type CreateJobPayload,
  type JobRecord,
  type UpdateJobPayload,
} from '@/lib/jobs-api';

export type JobActionKind = JobRecord['action_kind'];
export type JobTriggerKind = JobRecord['trigger_kind'];
export type JobScheduleKind = NonNullable<JobRecord['schedule_kind']>;

export interface JobActionFormFields {
  prompt: string;
  analysisCode: string;
}

export interface JobScheduleFormFields {
  intervalSeconds: string;
  runAt: string;
  cronExpression: string;
  cronTimezone: string;
}

export interface CreateJobFormState
  extends JobActionFormFields, JobScheduleFormFields {
  name: string;
  actionKind: JobActionKind;
  triggerKind: JobTriggerKind;
  scheduleKind: JobScheduleKind;
  thingId: string;
  eventName: string;
  subscriptionInput: string;
}

export interface EditJobFormState
  extends JobActionFormFields, JobScheduleFormFields {
  name: string;
  enabled: boolean;
  scheduleKind: JobScheduleKind;
}

export function defaultCronTimezone(): string {
  if (typeof Intl === 'undefined') return 'Europe/Berlin';
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Berlin';
}

export const INITIAL_CREATE_JOB_FORM: CreateJobFormState = {
  name: '',
  actionKind: 'prompt',
  triggerKind: 'time',
  scheduleKind: 'interval',
  prompt: '',
  analysisCode: '',
  intervalSeconds: '',
  runAt: '',
  cronExpression: '',
  cronTimezone: defaultCronTimezone(),
  thingId: '',
  eventName: '',
  subscriptionInput: '',
};

export function toDatetimeLocal(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (value: number) => String(value).padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

export function toEditJobFormState(job: JobRecord): EditJobFormState {
  return {
    name: job.name,
    prompt: job.prompt ?? '',
    analysisCode: job.analysis_code ?? '',
    scheduleKind: job.schedule_kind ?? 'interval',
    intervalSeconds:
      job.interval_seconds != null ? String(job.interval_seconds) : '',
    runAt: toDatetimeLocal(job.run_at),
    cronExpression: job.cron_expression ?? '',
    cronTimezone: job.cron_timezone ?? defaultCronTimezone(),
    enabled: job.enabled,
  };
}

export function canEditTimeSchedule(
  job: Pick<JobRecord, 'trigger_kind'>,
): boolean {
  return job.trigger_kind === 'time';
}

export function getSubscriptionInputError(
  form: Pick<CreateJobFormState, 'subscriptionInput' | 'triggerKind'>,
): string | null {
  if (form.triggerKind !== 'event' || !form.subscriptionInput.trim()) {
    return null;
  }
  try {
    JSON.parse(form.subscriptionInput);
    return null;
  } catch {
    return 'Subscription input must be valid JSON.';
  }
}

export function validateJobActionFields(
  actionKind: JobActionKind,
  form: JobActionFormFields,
): string | null {
  if (actionKind === 'prompt' && !form.prompt.trim()) {
    return 'Prompt is required.';
  }
  if (actionKind === 'analysis' && !form.analysisCode.trim()) {
    return 'Analysis code is required.';
  }
  return null;
}

export function validateTimeScheduleFields(
  scheduleKind: JobScheduleKind,
  form: JobScheduleFormFields,
): string | null {
  if (scheduleKind === 'interval') {
    const seconds = Number(form.intervalSeconds);
    if (
      !form.intervalSeconds.trim() ||
      !Number.isFinite(seconds) ||
      seconds < 1
    ) {
      return 'Interval must be a positive number of seconds.';
    }
  }
  if (scheduleKind === 'once' && !form.runAt.trim()) {
    return 'Run time is required for one-time jobs.';
  }
  if (scheduleKind === 'cron' && !form.cronExpression.trim()) {
    return 'Cron expression is required.';
  }
  return null;
}

export function validateCreateJobForm(form: CreateJobFormState): string | null {
  if (!form.name.trim()) return 'Name is required.';

  const actionError = validateJobActionFields(form.actionKind, form);
  if (actionError) return actionError;

  if (form.triggerKind === 'time') {
    return validateTimeScheduleFields(form.scheduleKind, form);
  }
  if (!form.thingId.trim()) return 'Thing ID is required for event jobs.';
  if (!form.eventName.trim()) return 'Event name is required for event jobs.';
  return null;
}

export function validateEditJobForm(
  job: JobRecord,
  form: EditJobFormState,
): string | null {
  if (!form.name.trim()) return 'Name is required.';

  const actionError = validateJobActionFields(job.action_kind, form);
  if (actionError) return actionError;

  return canEditTimeSchedule(job)
    ? validateTimeScheduleFields(form.scheduleKind, form)
    : null;
}

export function toCreateJobPayload(form: CreateJobFormState): CreateJobPayload {
  const payload: CreateJobPayload = {
    name: form.name.trim(),
    action_kind: form.actionKind,
    trigger_kind: form.triggerKind,
  };

  if (form.actionKind === 'analysis') {
    payload.analysis_code = form.analysisCode.trim();
  } else {
    payload.prompt = form.prompt.trim();
  }

  if (payload.trigger_kind === 'time') {
    payload.schedule_kind = form.scheduleKind;
    if (form.scheduleKind === 'interval' && form.intervalSeconds.trim()) {
      payload.interval_seconds = Number(form.intervalSeconds);
    }
    if (form.scheduleKind === 'once' && form.runAt.trim()) {
      payload.run_at = new Date(form.runAt).toISOString();
    }
    if (form.scheduleKind === 'cron' && form.cronExpression.trim()) {
      payload.cron_expression = form.cronExpression.trim();
      if (form.cronTimezone.trim()) {
        payload.cron_timezone = form.cronTimezone.trim();
      }
    }
  } else {
    payload.thing_id = form.thingId.trim();
    payload.event_name = form.eventName.trim();
    if (form.subscriptionInput.trim()) {
      payload.subscription_input = JSON.parse(form.subscriptionInput);
    }
  }

  return payload;
}

export function toUpdateJobPayload(
  job: JobRecord,
  form: EditJobFormState,
): UpdateJobPayload {
  const payload: UpdateJobPayload = {
    name: form.name.trim(),
    enabled: form.enabled,
  };
  if (job.action_kind === 'prompt') {
    payload.prompt = form.prompt.trim();
  } else {
    payload.analysis_code = form.analysisCode.trim();
  }

  const scheduleKind = canEditTimeSchedule(job) ? form.scheduleKind : null;
  if (scheduleKind) {
    payload.schedule_kind = scheduleKind;
  }
  if (scheduleKind === 'interval') {
    payload.interval_seconds = Number(form.intervalSeconds);
  }
  if (scheduleKind === 'once') {
    payload.run_at = new Date(form.runAt).toISOString();
  }
  if (scheduleKind === 'cron') {
    payload.cron_expression = form.cronExpression.trim();
    payload.cron_timezone = form.cronTimezone.trim();
  }

  return payload;
}
