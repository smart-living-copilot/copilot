import { httpClient, httpJson } from '@/lib/http-client';

export interface JobRecord {
  id: string;
  name: string;
  created_from_thread_id: string;
  job_thread_id: string;
  action_kind: 'prompt' | 'analysis';
  interaction_mode:
    | 'autonomous'
    | 'ask_when_needed'
    | 'required_checkin'
    | 'approval_gate';
  output_kind: 'narrative' | 'structured_record';
  prompt: string | null;
  analysis_code: string | null;
  record_schema: unknown | null;
  record_schema_version: number | null;
  virtual_thing_id: string | null;
  enabled: boolean;
  trigger_kind: 'time' | 'event';
  schedule_kind: 'once' | 'interval' | null;
  run_at: string | null;
  interval_seconds: number | null;
  next_run_at: string | null;
  thing_id: string | null;
  event_name: string | null;
  subscription_id: string | null;
  subscription_input: unknown | null;
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
  messages: JobThreadMessage[];
}

interface ListJobsResponse {
  jobs: JobRecord[];
}

interface ListJobRunsResponse {
  runs: JobRunRecord[];
}

export interface CreateJobPayload {
  name: string;
  created_from_thread_id?: string;
  action_kind: 'prompt' | 'analysis';
  interaction_mode?: 'autonomous' | 'ask_when_needed' | 'required_checkin' | 'approval_gate';
  output_kind?: 'narrative' | 'structured_record';
  prompt?: string;
  analysis_code?: string;
  record_schema?: unknown;
  record_schema_version?: number;
  virtual_thing_id?: string;
  virtual_thing_title?: string;
  virtual_thing_description?: string;
  trigger_kind: 'time' | 'event';
  schedule_kind?: 'once' | 'interval';
  run_at?: string;
  interval_seconds?: number;
  thing_id?: string;
  event_name?: string;
  subscription_input?: unknown;
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
  prompt?: string;
  analysis_code?: string;
  interval_seconds?: number;
  run_at?: string;
  enabled?: boolean;
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

export async function fetchJobRuns(jobId: string): Promise<JobRunRecord[]> {
  const json = await httpJson<ListJobRunsResponse>(
    `/jobs/${encodeURIComponent(jobId)}/runs`,
  );
  return json.runs;
}

export async function fetchJobThread(jobId: string): Promise<JobThreadRecord> {
  return httpJson<JobThreadRecord>(`/jobs/${encodeURIComponent(jobId)}/thread`);
}

export async function replyToJob(
  jobId: string,
  message: string,
): Promise<unknown> {
  return httpJson(`/jobs/${encodeURIComponent(jobId)}/reply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
}
