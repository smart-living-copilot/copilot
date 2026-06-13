"""Prompt templates for agent orchestration.

This package groups role-specific system prompts for routing, conversational
responses, control actions, analysis tasks, jobs execution, and standalone
virtual Thing authoring. The constants are consumed by graph construction in
:mod:`copilot.agent.builder`.
"""

from copilot.agent.prompts.analysis import ANALYSIS_PROMPT
from copilot.agent.prompts.control import CONTROL_PROMPT
from copilot.agent.prompts.jobs import JOBS_PROMPT
from copilot.agent.prompts.respond import RESPOND_PROMPT
from copilot.agent.prompts.router import ROUTER_PROMPT
from copilot.agent.prompts.virtual_things import VIRTUAL_THINGS_PROMPT

__all__ = [
    "ANALYSIS_PROMPT",
    "CONTROL_PROMPT",
    "JOBS_PROMPT",
    "RESPOND_PROMPT",
    "ROUTER_PROMPT",
    "VIRTUAL_THINGS_PROMPT",
]
