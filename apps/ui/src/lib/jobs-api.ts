import { httpClient, httpJson } from '@/lib/http-client';

export interface JobRecord {
  id: string;
  name: string;
  created_from_thread_id: string;
  job_thread_id: string;
  interaction_mode: JobInteractionMode;
  action: JobAction;
  trigger: JobTrigger;
  output: JobOutput;
  enabled: boolean;
  next_run_at: string | null;
  subscription_id: string | null;
  resource_health: JobResourceHealth | null;
  created_at: string;
  updated_at: string;
  last_run_id: string | null;
  last_run_at: string | null;
  last_run_status:
    | 'running'
    | 'succeeded'
    | 'failed'
    | 'waiting_for_input'
    | 'cancelled'
    | 'skipped'
    | null;
  last_error: string | null;
  last_response: string | null;
  run_count: number;
  active_run_id: string | null;
  active_run_started_at: string | null;
  active_run_source: 'manual' | 'time' | 'event' | null;
  waiting_question: string | null;
}

export type JobAction = PromptJobAction | AnalysisJobAction;

export interface PromptJobAction {
  kind: 'prompt';
  prompt: string;
}

export interface AnalysisJobAction {
  kind: 'analysis';
  analysis_code: string;
}

export type JobTrigger = TimeJobTrigger | EventJobTrigger;

export interface TimeJobTrigger {
  kind: 'time';
  schedule: JobSchedule;
}

export interface EventJobTrigger {
  kind: 'event';
  thing_id: string;
  event_name: string;
  subscription_input?: unknown | null;
}

export type JobSchedule =
  | OnceJobSchedule
  | IntervalJobSchedule
  | CronJobSchedule;

export interface OnceJobSchedule {
  kind: 'once';
  run_at: string;
}

export interface IntervalJobSchedule {
  kind: 'interval';
  interval_seconds: number;
}

export interface CronJobSchedule {
  kind: 'cron';
  expression: string;
  timezone?: string | null;
}

export type JobOutput = NarrativeJobOutput | StructuredRecordJobOutput;

export type JobInteractionMode = 'autonomous' | 'required_checkin';

export interface NarrativeJobOutput {
  kind: 'narrative';
}

export interface StructuredRecordJobOutput {
  kind: 'structured_record';
  schema: unknown;
  schema_version: number;
  virtual_thing?: {
    id?: string | null;
    title?: string | null;
    description?: string | null;
  } | null;
}

export interface JobDefinitionPayload {
  interaction_mode?: JobInteractionMode;
  action: JobAction;
  trigger: JobTrigger;
  output: JobOutput;
}

export interface JobResourceHealthEntry {
  status: 'healthy' | 'degraded' | string;
  checked_at?: string;
  message?: string;
}

export interface JobResourceHealth {
  status: 'healthy' | 'degraded' | string;
  checked_at?: string;
  last_error?: string;
  resources?: Record<string, JobResourceHealthEntry>;
}

export interface JobRunRecord {
  id: string;
  job_id: string;
  job_thread_id: string;
  source: 'manual' | 'time' | 'event';
  status:
    | 'running'
    | 'succeeded'
    | 'failed'
    | 'waiting_for_input'
    | 'cancelled'
    | 'skipped';
  trigger_payload: unknown;
  result: unknown | null;
  error: string | null;
  response_text: string | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
}

export type JobRunEventType =
  | 'run_started'
  | 'user_reply'
  | 'waiting_for_input'
  | 'assistant_message'
  | 'record_submitted'
  | 'run_succeeded'
  | 'run_failed'
  | 'run_cancelled'
  | 'run_skipped';

export interface JobRunEventRecord {
  id: number;
  job_id: string;
  run_id: string;
  event_type: JobRunEventType;
  message: string | null;
  payload: unknown | null;
  created_at: string;
}

export interface JobThreadMessage {
  id?: string;
  role?: string;
  content?: unknown;
  type?: string;
  name?: string;
}

export interface JobThreadRecord {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  kind?: 'chat' | 'job';
  visible?: boolean;
  jobId?: string | null;
  job: JobRecord;
  run?: JobRunRecord | null;
  events: JobRunEventRecord[];
  messages: JobThreadMessage[];
}

interface ListJobsResponse {
  jobs: JobRecord[];
}

interface ListJobRunsResponse {
  runs: JobRunRecord[];
  total?: number;
  limit?: number;
  offset?: number;
}

interface ListJobRunEventsResponse {
  events: JobRunEventRecord[];
}

export interface CreateJobPayload {
  name: string;
  created_from_thread_id?: string;
  interaction_mode?: JobInteractionMode;
  action: JobAction;
  trigger: JobTrigger;
  output?: JobOutput;
}

export async function fetchJobs(threadId?: string): Promise<JobRecord[]> {
  const query = new URLSearchParams();
  if (threadId?.trim()) {
    query.set('created_from_thread_id', threadId.trim());
  }

  const suffix = query.toString();
  const json = await httpJson<ListJobsResponse>(
    `/jobs${suffix ? `?${suffix}` : ''}`,
  );
  return json.jobs;
}

export async function createJob(payload: CreateJobPayload): Promise<JobRecord> {
  return httpJson<JobRecord>('/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function fetchJob(jobId: string): Promise<JobRecord> {
  return httpJson<JobRecord>(`/jobs/${encodeURIComponent(jobId)}`);
}

export interface UpdateJobPayload {
  name?: string;
  enabled?: boolean;
  definition?: JobDefinitionPayload;
}

export async function updateJob(
  jobId: string,
  payload: UpdateJobPayload,
): Promise<JobRecord> {
  return httpJson<JobRecord>(`/jobs/${encodeURIComponent(jobId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function setJobEnabled(
  jobId: string,
  enabled: boolean,
): Promise<JobRecord> {
  return updateJob(jobId, { enabled });
}

interface CancelJobResponse {
  ok: boolean;
  job: JobRecord;
}

export async function cancelJobRun(jobId: string): Promise<JobRecord> {
  const json = await httpJson<CancelJobResponse>(
    `/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: 'POST' },
  );
  return json.job;
}

export async function deleteJob(jobId: string): Promise<void> {
  await httpClient(`/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' });
}

export async function runJobNow(jobId: string): Promise<unknown> {
  return httpJson(`/jobs/${encodeURIComponent(jobId)}/run`, {
    method: 'POST',
  });
}

export interface JobRunPage {
  runs: JobRunRecord[];
  total: number;
  limit: number;
  offset: number;
}

export interface FetchJobRunsOptions {
  limit?: number;
  offset?: number;
}

export async function fetchJobRunsPage(
  jobId: string,
  options: FetchJobRunsOptions = {},
): Promise<JobRunPage> {
  const query = new URLSearchParams();
  if (options.limit != null) {
    query.set('limit', String(options.limit));
  }
  if (options.offset != null) {
    query.set('offset', String(options.offset));
  }

  const suffix = query.toString();
  const json = await httpJson<ListJobRunsResponse>(
    `/jobs/${encodeURIComponent(jobId)}/runs${suffix ? `?${suffix}` : ''}`,
  );
  return {
    runs: json.runs,
    total: json.total ?? json.runs.length,
    limit: json.limit ?? json.runs.length,
    offset: json.offset ?? 0,
  };
}

export async function fetchJobRuns(
  jobId: string,
  options?: FetchJobRunsOptions,
): Promise<JobRunRecord[]> {
  const page = await fetchJobRunsPage(jobId, options);
  return page.runs;
}

export async function fetchJobRunEvents(
  jobId: string,
): Promise<JobRunEventRecord[]> {
  const json = await httpJson<ListJobRunEventsResponse>(
    `/jobs/${encodeURIComponent(jobId)}/run-events`,
  );
  return json.events;
}

export async function fetchJobThread(jobId: string): Promise<JobThreadRecord> {
  return httpJson<JobThreadRecord>(`/jobs/${encodeURIComponent(jobId)}/thread`);
}

export function createClientReplyId(): string {
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.randomUUID === 'function'
  ) {
    return crypto.randomUUID();
  }
  return `reply-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function replyToJob(
  jobId: string,
  message: string,
  clientReplyId: string = createClientReplyId(),
): Promise<unknown> {
  return httpJson(`/jobs/${encodeURIComponent(jobId)}/reply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, client_reply_id: clientReplyId }),
  });
}
