"""Automation jobs domain.

Jobs are background automations created by the agent or the jobs UI. A job has
three nested definition concepts:

* ``trigger`` says when it runs: time-based schedules or WoT events.
* ``action`` says what it does: prompt jobs invoke the LangGraph agent, while
  analysis jobs run deterministic Python in the code-executor service.
* ``output`` says what the run produces: narrative text or a structured record
  that is exposed through a generic virtual Thing.

The API layer in ``routes`` delegates to ``JobService``. The service validates
requests, creates external schedules/subscriptions, starts Taskiq jobs, and
reconciles stale runs on startup. ``JobStore`` owns the transactional Postgres
state: job definitions, job run history, active-run leases, duplicate-run
skips, waiting questions, canonical run events, and hidden per-job thread
metadata.

Prompt jobs run through ``JobExecutor`` using a normal Postgres LangGraph
checkpointer and hidden per-run ``job:{job_id}:run:{run_id}`` threads. They can
pause through the worker-only ``ask_job_user`` tool, which raises a LangGraph
interrupt and lets ``POST /jobs/{job_id}/reply`` resume the same checkpoint
thread. User-facing job timelines come from ``job_run_events``; LangGraph
checkpoints remain runtime state and legacy transcript fallback. Analysis jobs
bypass LangGraph and store their code-executor output in ``job_runs.result``.

Redis is used for Taskiq scheduling, Taskiq results, WoT event fan-out, catalog
Thing events, and job run SSE notifications. Structured-record jobs keep their
record rows in the jobs domain while registering record-backed bindings through
``copilot.virtual_things`` so runtime dispatch stays on the generic virtual
Thing path.
"""
