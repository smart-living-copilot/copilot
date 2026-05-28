import { httpClient, httpJson } from '@/lib/http-client';

export interface JobRecord {
  id: string;
  name: string;
  thread_id: string;
  job_type: 'prompt' | 'analysis';
  prompt: string | null;
  analysis_code: string | null;
  enabled: boolean;
  trigger_type: 'time' | 'event';
  run_at: string | null;
  interval_seconds: number | null;
  next_run_at: string | null;
  thing_id: string | null;
  event_name: string | null;
  subscription_id: string | null;
  subscription_input: unknown | null;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
  last_error: string | null;
  last_response: string | null;
  run_count: number;
  last_fetch_value: string | null;
}

interface ListJobsResponse {
  jobs: JobRecord[];
}

export interface CreateJobPayload {
  name: string;
  thread_id: string;
  job_type: 'prompt' | 'analysis';
  prompt?: string;
  analysis_code?: string;
  trigger_type: 'time' | 'event';
  run_at?: string;
  interval_seconds?: number;
  thing_id?: string;
  event_name?: string;
  subscription_input?: unknown;
}

export async function fetchJobs(threadId?: string): Promise<JobRecord[]> {
  const query = new URLSearchParams();
  if (threadId?.trim()) {
    query.set('thread_id', threadId.trim());
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

export async function deleteJob(jobId: string): Promise<void> {
  await httpClient(`/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' });
}

export async function runJobNow(jobId: string): Promise<unknown> {
  return httpJson(`/jobs/${encodeURIComponent(jobId)}/run`, {
    method: 'POST',
  });
}