"""Smart Living Copilot agent domain.

The agent package hosts the LangGraph orchestration layer that powers conversational
interactions and background execution. Incoming messages are routed into one of
chat, control, analysis, or jobs flows, then passed through stateful LLM + tool
loops with checkpoint-backed persistence.

The module-level API in this package exposes:

* ``build_graph`` for foreground interactions (chat UI and API call paths).
* ``build_background_job_graph`` for worker-driven prompt jobs that may
  perform tool calls, wait for ``ask_job_user``, and then resume from checkpointed
  threads.

Graph construction is implemented in :mod:`copilot.agent.builder`; nodes and
prompts live in :mod:`copilot.agent.nodes` and :mod:`copilot.agent.prompts` and
are composed here into the exported entrypoints.
"""

from copilot.agent.builder import build_background_job_graph, build_graph

__all__ = ["build_background_job_graph", "build_graph"]
