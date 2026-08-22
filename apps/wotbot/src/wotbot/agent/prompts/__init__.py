"""Prompt templates for agent orchestration.

This package groups role-specific system prompts for routing, conversational
responses, control actions, analysis tasks, jobs execution, standalone virtual
Thing authoring, and automatic discovery of Thing Descriptions.

The constants are consumed by graph construction in :mod:`wotbot.agent.builder`.
"""

from wotbot.agent.prompts.analysis import ANALYSIS_PROMPT
from wotbot.agent.prompts.control import CONTROL_PROMPT
from wotbot.agent.prompts.discovery import DISCOVERY_PROMPT
from wotbot.agent.prompts.handoff import HANDOFF_PROMPT
from wotbot.agent.prompts.jobs import JOBS_PROMPT
from wotbot.agent.prompts.respond import RESPOND_PROMPT
from wotbot.agent.prompts.router import ROUTER_PROMPT
from wotbot.agent.prompts.virtual_things import VIRTUAL_THINGS_PROMPT
from wotbot.agent.prompts.voice import VOICE_RESPONSE_PROMPT

__all__ = [
    "ANALYSIS_PROMPT",
    "CONTROL_PROMPT",
    "DISCOVERY_PROMPT",
    "HANDOFF_PROMPT",
    "JOBS_PROMPT",
    "RESPOND_PROMPT",
    "ROUTER_PROMPT",
    "VIRTUAL_THINGS_PROMPT",
    "VOICE_RESPONSE_PROMPT",
]
