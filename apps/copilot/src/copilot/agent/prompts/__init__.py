"""Prompt templates for agent orchestration.

This package groups role-specific system prompts for routing, conversational
responses, control actions, analysis tasks, and jobs execution. The constants are
consumed by graph construction in :mod:`copilot.agent.builder`.
"""

from copilot.agent.prompts.router import ROUTER_PROMPT
from copilot.agent.prompts.respond import RESPOND_PROMPT
from copilot.agent.prompts.control import CONTROL_PROMPT
from copilot.agent.prompts.analysis import ANALYSIS_PROMPT
from copilot.agent.prompts.jobs import JOBS_PROMPT

__all__ = [
    "ROUTER_PROMPT",
    "RESPOND_PROMPT",
    "CONTROL_PROMPT",
    "ANALYSIS_PROMPT",
    "JOBS_PROMPT",
]
