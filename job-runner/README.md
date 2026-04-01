# Job Runner

`job-runner` is a standalone service that executes automation jobs for Smart Living Copilot.

It supports:
- Time-triggered jobs (`run_at` and optional `interval_seconds`)
- WoT event-triggered jobs (subscribed through `wot-runtime`)

When a trigger fires, `job-runner` sends the job prompt into the copilot thread through:
- `POST /internal/jobs/dispatch` on `copilot`

## API

### `POST /jobs`
Create a job.

Example payload:

```json
{
  "name": "Alert on motion",
  "thread_id": "my-chat-thread",
  "prompt": "Motion detected. Summarize and suggest next action.",
  "trigger_type": "event",
  "thing_id": "front-door-sensor",
  "event_name": "motion"
}
```

### `GET /jobs`
List jobs, optionally filtered by `thread_id`.

### `DELETE /jobs/{job_id}`
Delete a job and remove its runtime subscription if present.

### `POST /jobs/{job_id}/run`
Manual trigger for a job.

### `GET /ui`
Minimal dashboard for queue visibility.

- Shows queued, scheduled, and waiting-event counts
- Shows each job's latest `Last Answer` from the agent
- Auto-refreshes every 5 seconds

## Environment

- `JOBS_DB_PATH` default `/data/jobs.db`
- `REDIS_URL` default `redis://valkey:6379`
- `WOT_RUNTIME_STREAM` default `wot_runtime_events`
- `JOBS_EVENTS_GROUP` default `job_runner`
- `JOBS_EVENTS_CONSUMER` default `job_runner_1`
- `WOT_RUNTIME_URL` default `http://wot-runtime:3003`
- `WOT_RUNTIME_API_TOKEN` runtime bearer token
- `COPILOT_URL` default `http://copilot:8123`
- `INTERNAL_API_KEY` shared key for internal calls
