"""A2A (Agent-to-Agent) protocol types and JSON-RPC implementation for WoTBot.

Implements the Google A2A protocol (JSON-RPC 2.0) so any A2A-compatible agent
can interact with WoTBot — send messages, receive responses, and retrieve
visualizations as artifacts.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REQUIRES_INPUT = "requires_input"


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


# ---------------------------------------------------------------------------
# Parts — content units inside a Message
# ---------------------------------------------------------------------------


class Part(BaseModel):
    """A single part of a message.

    Artifact content can be delivered in three ways (in order of preference):
    1. ``url`` — a resolvable URL for direct browser/fetch access
    2. ``inline_data`` — base64-encoded content for agents without out-of-band access
    3. ``text`` — plain text content
    """

    text: str = ""
    mime_type: str = "text/plain"
    file_name: str = ""
    url: str = ""  # Resolvable URL for direct access
    inline_data: str = ""  # Base64-encoded content
    inline_data_mime_type: str = ""


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class Message(BaseModel):
    """A message in a conversation."""

    role: Role = Role.USER
    parts: list[Part] = []
    message_id: str = ""
    context_id: str = ""


# ---------------------------------------------------------------------------
# TaskStatus
# ---------------------------------------------------------------------------


class TaskStatus(BaseModel):
    """Status of a task."""

    state: TaskState = TaskState.WORKING
    message: Message | None = None


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------


class Artifact(BaseModel):
    """An artifact produced by the agent (e.g. a plot, image, file)."""

    artifact_id: str = ""
    name: str = ""
    description: str = ""
    parts: list[Part] = []


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


class Task(BaseModel):
    """A task represents a single agent execution."""

    id: str = ""
    context_id: str = ""
    status: TaskStatus = TaskStatus()
    artifacts: list[Artifact] = []
    history: list[Message] = []


# ---------------------------------------------------------------------------
# JSON-RPC request / response
# ---------------------------------------------------------------------------


class JSONRPCRequest(BaseModel):
    """A JSON-RPC 2.0 request."""

    jsonrpc: str = "2.0"
    id: str = ""
    method: str = ""
    params: dict[str, Any] = {}


class JSONRPCError(BaseModel):
    """A JSON-RPC 2.0 error object."""

    code: int = 0
    message: str = ""
    data: Any = None


class JSONRPCResponse(BaseModel):
    """A JSON-RPC 2.0 response."""

    jsonrpc: str = "2.0"
    id: str = ""
    result: Any = None
    error: JSONRPCError | None = None


# ---------------------------------------------------------------------------
# A2A-specific request / response payloads
# ---------------------------------------------------------------------------


class SendMessageParams(BaseModel):
    """Parameters for the ``sendMessage`` method."""

    message: Message = Message()
    context_id: str = ""
    task_id: str = ""
    push_notification: dict[str, Any] = {}


class SendMessageResult(BaseModel):
    """Result of a ``sendMessage`` call."""

    task: Task = Task()


# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------


class AgentCapability(BaseModel):
    """A capability the agent advertises."""

    name: str = ""
    description: str = ""


class AgentSkill(BaseModel):
    """A skill the agent can perform."""

    id: str = ""
    name: str = ""
    description: str = ""
    tags: list[str] = []
    examples: list[str] = []


class AgentCard(BaseModel):
    """The well-known agent card describing the agent."""

    name: str = "WoTBot"
    description: str = "Conversational Web of Things assistant"
    url: str = ""
    version: str = "1.0.0"
    capabilities: list[AgentCapability] = []
    skills: list[AgentSkill] = []
    default_input_modes: list[str] = ["text"]
    default_output_modes: list[str] = ["text", "image/png", "text/html"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_text_part(text: str) -> Part:
    return Part(text=text, mime_type="text/plain")


def make_image_part(base64_data: str, mime_type: str = "image/png", url: str = "") -> Part:
    return Part(
        text="",
        mime_type=mime_type,
        url=url,
        inline_data=base64_data,
        inline_data_mime_type=mime_type,
    )


def make_html_part(html: str) -> Part:
    return Part(text="", mime_type="text/html", inline_data=html)


def make_message(text: str, role: Role = Role.USER) -> Message:
    return Message(
        role=role,
        parts=[make_text_part(text)],
        message_id=str(uuid4()),
    )


# ---------------------------------------------------------------------------
# WoTBot agent card factory
# ---------------------------------------------------------------------------


def wotbot_agent_card(base_url: str = "") -> AgentCard:
    """Build the WoTBot agent card."""
    return AgentCard(
        name="WoTBot",
        description="Conversational Web of Things assistant — query devices, "
        "run analysis code, generate visualizations, and control your smart home.",
        url=base_url,
        version="1.1.0",
        capabilities=[
            AgentCapability(name="chat", description="General conversation"),
            AgentCapability(name="wot-runtime", description="WoT device interaction"),
            AgentCapability(name="code-execution", description="Run Python analysis code"),
            AgentCapability(name="visualization", description="Generate plots and charts"),
        ],
        skills=[
            AgentSkill(
                id="device_query",
                name="Device Query",
                description="Query device properties and sensor readings",
                tags=["wot", "iot", "sensors"],
                examples=["What is the temperature in the kitchen?", "Show me all devices"],
            ),
            AgentSkill(
                id="data_analysis",
                name="Data Analysis",
                description="Run Python code to analyze and visualize data",
                tags=["analysis", "plotting", "code"],
                examples=["Plot energy usage for the last 24 hours", "Analyze temperature trends"],
            ),
            AgentSkill(
                id="device_control",
                name="Device Control",
                description="Control smart home devices",
                tags=["control", "actuators"],
                examples=["Turn on the living room light", "Set thermostat to 22°C"],
            ),
        ],
        default_input_modes=["text"],
        default_output_modes=["text", "image/png", "text/html"],
    )