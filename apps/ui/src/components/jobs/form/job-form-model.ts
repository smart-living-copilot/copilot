import {
  type CreateJobPayload,
  type EventJobTrigger,
  type JobRecord,
  type JobSchedule,
  type UpdateJobPayload,
} from '@/lib/jobs-api';

export type JobActionKind = JobRecord['action']['kind'];
export type JobTriggerKind = JobRecord['trigger']['kind'];
export type JobScheduleKind = JobSchedule['kind'];

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
  const schedule = job.trigger.kind === 'time' ? job.trigger.schedule : null;
  return {
    name: job.name,
    prompt: job.action.kind === 'prompt' ? job.action.prompt : '',
    analysisCode:
      job.action.kind === 'analysis' ? job.action.analysis_code : '',
    scheduleKind: schedule?.kind ?? 'interval',
    intervalSeconds:
      schedule?.kind === 'interval' ? String(schedule.interval_seconds) : '',
    runAt: toDatetimeLocal(schedule?.kind === 'once' ? schedule.run_at : null),
    cronExpression: schedule?.kind === 'cron' ? schedule.expression : '',
    cronTimezone:
      schedule?.kind === 'cron'
        ? (schedule.timezone ?? defaultCronTimezone())
        : defaultCronTimezone(),
    enabled: job.enabled,
  };
}

export function canEditTimeSchedule(job: Pick<JobRecord, 'trigger'>): boolean {
  return job.trigger.kind === 'time';
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

  const actionError = validateJobActionFields(job.action.kind, form);
  if (actionError) return actionError;

  return canEditTimeSchedule(job)
    ? validateTimeScheduleFields(form.scheduleKind, form)
    : null;
}

export function toCreateJobPayload(form: CreateJobFormState): CreateJobPayload {
  const payload: CreateJobPayload = {
    name: form.name.trim(),
    action:
      form.actionKind === 'analysis'
        ? { kind: 'analysis', analysis_code: form.analysisCode.trim() }
        : { kind: 'prompt', prompt: form.prompt.trim() },
    trigger:
      form.triggerKind === 'time'
        ? { kind: 'time', schedule: schedulePayload(form) }
        : eventTriggerPayload(form),
    output: { kind: 'narrative' },
  };

  return payload;
}

export function toUpdateJobPayload(
  job: JobRecord,
  form: EditJobFormState,
): UpdateJobPayload {
  const payload: UpdateJobPayload = {
    name: form.name.trim(),
    enabled: form.enabled,
    definition: {
      interaction_mode: job.interaction_mode,
      action:
        job.action.kind === 'analysis'
          ? { kind: 'analysis', analysis_code: form.analysisCode.trim() }
          : { kind: 'prompt', prompt: form.prompt.trim() },
      trigger:
        job.trigger.kind === 'time'
          ? { kind: 'time', schedule: schedulePayload(form) }
          : job.trigger,
      output: job.output,
    },
  };

  return payload;
}

function schedulePayload(
  form: JobScheduleFormFields & { scheduleKind: JobScheduleKind },
): JobSchedule {
  if (form.scheduleKind === 'once') {
    return { kind: 'once', run_at: new Date(form.runAt).toISOString() };
  }
  if (form.scheduleKind === 'cron') {
    return {
      kind: 'cron',
      expression: form.cronExpression.trim(),
      timezone: form.cronTimezone.trim() || null,
    };
  }
  return { kind: 'interval', interval_seconds: Number(form.intervalSeconds) };
}

function eventTriggerPayload(form: CreateJobFormState): EventJobTrigger {
  const trigger: EventJobTrigger = {
    kind: 'event' as const,
    thing_id: form.thingId.trim(),
    event_name: form.eventName.trim(),
  };
  if (form.subscriptionInput.trim()) {
    trigger.subscription_input = JSON.parse(form.subscriptionInput);
  }
  return trigger;
}
