# Job Runner

`job-runner` is a standalone service that executes automation jobs for Smart Living Copilot.

It supports:
- Time-triggered jobs (`run_at` and optional `interval_seconds`)
- WoT event-triggered jobs (subscribed through `wot-runtime`)
- Periodic analysis jobs (`job_type: "analysis"`) executed in `code-executor`

When a trigger fires, `job-runner` sends the job prompt into the copilot thread through:
- `POST /internal/jobs/dispatch` on `copilot`

## How It Fits Together

```text
User chat
   |
   v
 chat-ui
   |
   v
 copilot -- create/list/run/delete jobs --> job-runner
                                            |      \
                                            |       \
                                            |        +--> code-executor (analysis jobs)
                                            |
                                            +--> wot-runtime events / time scheduler
                                                     |
                                                     v
                                                trigger fires

trigger fires
   |
   +--> prompt job    --> job-runner --> copilot thread
   |
   +--> analysis job  --> job-runner --> code-executor --> last result in UI
```

## How The Job System Works

There are two job types:

- `prompt` jobs: when triggered, `job-runner` sends the saved prompt into an existing `copilot` thread
- `analysis` jobs: when triggered, `job-runner` runs the saved `analysis_code` in `code-executor`

There are two trigger modes:

- `time`: the job runs once at `run_at` or repeatedly every `interval_seconds`
- `event`: the job subscribes to a WoT event through `wot-runtime` and runs when that event arrives

Lifecycle of a job:

1. `copilot` creates the job by calling `POST /jobs` on `job-runner`.
2. `job-runner` stores the job in SQLite.
3. For time jobs, `job-runner` computes and stores `next_run_at`.
4. For event jobs, `job-runner` creates a WoT runtime subscription and stores the returned `subscription_id`.
5. A background scheduler checks due time jobs.
6. A background stream consumer listens for WoT runtime events from Valkey/Redis Streams.
7. When a trigger fires, `job-runner` executes the job:
  - prompt job -> dispatch to `copilot`
  - analysis job -> execute in `code-executor`
8. After execution, `job-runner` updates the stored job state with the latest result fields.

## Where Jobs Are Saved

Jobs are persisted in a SQLite database at:

- `JOBS_DB_PATH`
- default: `/data/jobs.db`

In Docker Compose this path is backed by the persistent volume mounted for `job-runner`, so jobs survive service restarts.

Each job row stores:

- identity: `id`, `name`, `thread_id`
- type/config: `job_type`, `prompt`, `analysis_code`
- trigger config: `trigger_type`, `run_at`, `interval_seconds`, `thing_id`, `event_name`, `subscription_id`
- scheduling state: `enabled`, `next_run_at`
- audit/result state: `last_run_at`, `last_error`, `last_response`, `run_count`, `last_fetch_value`
- timestamps: `created_at`, `updated_at`

## What "Last Result" Means

The UI shows the latest stored execution outcome for each job.

- For `prompt` jobs, `Last Result` is the assistant text returned by `copilot`
- For `analysis` jobs, `Last Result` is a summary built from `code-executor` output
  such as stdout, image count, or Plotly count

Related fields:

- `last_response`: latest successful result shown in the UI
- `last_error`: latest failure message, if a run failed
- `last_fetch_value`: optional extracted latest value for analysis jobs
- `run_count`: total number of times the job has been executed

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

Periodic analysis job example:

```json
{
  "name": "Check average temperature",
  "thread_id": "analysis-thread",
  "job_type": "analysis",
  "trigger_type": "time",
  "interval_seconds": 300,
  "analysis_code": "data = wot.read_property('thermostat', 'temperature'); print(data)"
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
- Shows each job's latest result output, including analysis job stdout summaries
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
- `CODE_EXECUTOR_URL` default `http://code-executor:8888`
- `INTERNAL_API_KEY` shared key for internal calls
