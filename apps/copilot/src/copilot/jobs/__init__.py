"""Automation jobs domain.

Jobs are background automations created by the agent or the jobs UI. A job has
two independent concepts:

* ``trigger_kind`` says when it runs: time-based schedules or WoT events.
* ``action_kind`` says what it does: prompt jobs invoke the LangGraph agent,
  while analysis jobs run deterministic Python in the code-executor service.

The API layer in ``routes`` delegates to ``JobService``. The service validates
requests, creates external schedules/subscriptions, starts Taskiq jobs, and
reconciles stale runs on startup. ``JobStore`` owns the transactional Postgres
state: job definitions, job run history, active-run leases, duplicate-run
skips, waiting questions, and hidden per-job thread metadata.

Prompt jobs run through ``JobExecutor`` using a normal Postgres LangGraph
checkpointer and hidden per-run ``job:{job_id}:run:{run_id}`` threads. They can
pause through the worker-only ``ask_job_user`` tool, which raises a LangGraph
interrupt and lets ``POST /jobs/{job_id}/reply`` resume the same checkpoint
thread. Analysis jobs bypass LangGraph and store their code-executor output in
``job_runs.result``.

Redis is used for Taskiq scheduling, Taskiq results, WoT event fan-out, and job
run SSE notifications. The current schema is fresh-reset oriented for local
development; old job tables should be dropped/reset rather than migrated.
"""
