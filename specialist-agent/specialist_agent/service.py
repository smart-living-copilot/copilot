"""Core service logic for discovering and executing specialist agents from TDs."""

import json
from dataclasses import dataclass
from typing import Any
import logging
import os
import re
import httpx
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

from specialist_agent.models import AgentSearchResult, ExecuteResponse, Settings

logger = logging.getLogger(__name__)


@dataclass
class AgentDefinition:
    id: str
    title: str
    description: str
    tags: list[str]
    score: float
    system_prompt: str
    llm: dict[str, Any]
    mcp_servers: list[dict[str, Any]]


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(p for p in parts if p).strip()
    return str(content)


def _tokenize(value: str) -> set[str]:
    return {token for token in value.lower().replace("_", " ").split() if token}


def _agent_extension(td: dict[str, Any]) -> dict[str, Any]:
    extension = td.get("x-copilot-agent")
    if isinstance(extension, dict):
        return extension
    extension = td.get("x-agent")
    return extension if isinstance(extension, dict) else {}


def _expand_env(value: str) -> str:
    """Expand ``${VAR_NAME}`` references from the process environment.

    Unknown variables are left as-is so misconfigurations are visible.
    """

    def _replace(m: re.Match) -> str:
        return os.environ.get(m.group(1), m.group(0))

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", _replace, value)


def _is_agent_td(item: dict[str, Any]) -> bool:
    tags = item.get("tags", [])
    if isinstance(tags, list) and any(str(tag).lower() == "agent" for tag in tags):
        return True

    td = item.get("document")
    if not isinstance(td, dict):
        return False

    at_type = td.get("@type")
    if isinstance(at_type, str) and at_type.lower() == "agent":
        return True
    if isinstance(at_type, list) and any(str(v).lower() == "agent" for v in at_type):
        return True

    return bool(_agent_extension(td))


def _score_candidate(item: dict[str, Any], query: str) -> float:
    title = str(item.get("title", ""))
    description = str(item.get("description", ""))
    tags = " ".join(str(tag) for tag in item.get("tags", []) if isinstance(tag, str))
    haystack = f"{title} {description} {tags}".strip()

    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0

    overlap = q_tokens & _tokenize(haystack)
    if not overlap:
        return 0.0

    return len(overlap) / len(q_tokens)


def _agent_from_item(item: dict[str, Any], query: str) -> AgentDefinition:
    td = item.get("document") if isinstance(item.get("document"), dict) else {}
    ext = _agent_extension(td)

    system_prompt = (
        ext.get("system_prompt")
        or ext.get("systemPrompt")
        or item.get("description")
        or "You are a specialist assistant."
    )

    llm = ext.get("llm") if isinstance(ext.get("llm"), dict) else {}
    mcp_servers = ext.get("mcp_servers")
    if not isinstance(mcp_servers, list):
        mcp_servers = ext.get("mcpServers") if isinstance(ext.get("mcpServers"), list) else []

    return AgentDefinition(
        id=str(item.get("id", "")),
        title=str(item.get("title", "")),
        description=str(item.get("description", "")),
        tags=[str(tag) for tag in item.get("tags", []) if isinstance(tag, str)],
        score=_score_candidate(item, query),
        system_prompt=str(system_prompt),
        llm=llm,
        mcp_servers=[server for server in mcp_servers if isinstance(server, dict)],
    )


class SpecialistService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _registry_headers(self) -> dict[str, str]:
        if not self.settings.wot_registry_token:
            return {"Accept": "application/json"}
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.settings.wot_registry_token}",
        }

    async def _fetch_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        timeout = float(self.settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{self.settings.wot_registry_api_url.rstrip('/')}{path}",
                params=params,
                headers=self._registry_headers(),
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def list_agents(self, query: str) -> list[AgentSearchResult]:
        payload = await self._fetch_json(
            "/things",
            params={
                "page": 1,
                "per_page": self.settings.max_agents_scan,
                "q": query,
            },
        )
        raw_items = payload.get("items")
        items = raw_items if isinstance(raw_items, list) else []

        agents: list[AgentSearchResult] = []
        for item in items:
            if not isinstance(item, dict) or not _is_agent_td(item):
                continue
            definition = _agent_from_item(item, query)
            if not definition.id or definition.score <= 0:
                continue
            agents.append(
                AgentSearchResult(
                    id=definition.id,
                    title=definition.title,
                    description=definition.description,
                    tags=definition.tags,
                    score=definition.score,
                )
            )

        agents.sort(key=lambda agent: agent.score, reverse=True)
        return agents

    async def _load_agent_by_id(self, agent_id: str, query: str) -> AgentDefinition:
        payload = await self._fetch_json(f"/things/{agent_id}")
        if not _is_agent_td(payload):
            raise ValueError(f"Thing {agent_id} is not an agent Thing Description")

        definition = _agent_from_item(payload, query)
        definition.score = max(definition.score, 1.0)
        return definition

    async def _select_agent(self, query: str, preferred_agent_id: str | None) -> AgentDefinition:
        if preferred_agent_id:
            return await self._load_agent_by_id(preferred_agent_id, query)

        agents = await self.list_agents(query)
        if not agents:
            raise ValueError("No matching specialist agent Thing Description found")

        top = agents[0]
        return await self._load_agent_by_id(top.id, query)

    def _make_llm(self, config: dict[str, Any]) -> ChatOpenAI:
        model = str(config.get("model") or self.settings.openai_model)
        api_key = str(config.get("api_key") or self.settings.openai_api_key)
        base_url = str(config.get("base_url") or self.settings.openai_base_url or "")
        temperature = float(config.get("temperature", self.settings.default_temperature))

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url or None,
            temperature=temperature,
            timeout=float(self.settings.request_timeout_seconds),
            max_retries=2,
        )

    def _mcp_connections(self, servers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        connections: dict[str, dict[str, Any]] = {}
        for index, server in enumerate(servers, start=1):
            name = server.get("name")
            server_name = str(name) if isinstance(name, str) and name else f"server_{index}"
            transport = str(server.get("transport") or "streamable_http")

            if transport == "stdio":
                connection = self._stdio_connection(server, server_name)
            else:
                connection = self._http_connection(server, server_name, transport)

            if connection is None:
                continue
            connections[server_name] = connection

        return connections

    def _stdio_connection(
        self, server: dict[str, Any], server_name: str
    ) -> dict[str, Any] | None:
        """Build a stdio MCP connection dict, or return None to skip."""
        command = server.get("command")
        if not isinstance(command, str) or not command:
            logger.warning("Skipping stdio MCP %r: missing 'command'", server_name)
            return None

        allowlist = self.settings.stdio_command_allowlist
        if allowlist:
            permitted = {c.strip() for c in allowlist.split(",") if c.strip()}
            if command not in permitted:
                logger.warning(
                    "Skipping stdio MCP %r: command %r not in STDIO_COMMAND_ALLOWLIST",
                    server_name,
                    command,
                )
                return None

        connection: dict[str, Any] = {"transport": "stdio", "command": command}

        args = server.get("args")
        if isinstance(args, list):
            connection["args"] = [
                _expand_env(str(a))
                for a in args
                if isinstance(a, (str, int, float))
            ]

        env = server.get("env")
        if isinstance(env, dict):
            connection["env"] = {
                str(k): _expand_env(str(v))
                for k, v in env.items()
                if isinstance(k, str) and isinstance(v, (str, int, float, bool))
            }

        return connection

    def _http_connection(
        self, server: dict[str, Any], server_name: str, transport: str
    ) -> dict[str, Any] | None:
        """Build an HTTP/SSE MCP connection dict, or return None to skip."""
        url = server.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            logger.warning("Skipping HTTP MCP %r: invalid or missing 'url'", server_name)
            return None

        connection: dict[str, Any] = {"transport": transport, "url": url}

        headers = server.get("headers")
        if isinstance(headers, dict):
            connection["headers"] = {
                str(k): _expand_env(str(v))
                for k, v in headers.items()
                if isinstance(k, (str, int, float)) and isinstance(v, (str, int, float))
            }

        return connection

    async def _run_with_tools(
        self,
        llm: ChatOpenAI,
        query: str,
        system_prompt: str,
        mcp_servers: list[dict[str, Any]],
        max_turns: int,
    ) -> tuple[str, int]:
        connections = self._mcp_connections(mcp_servers)
        if not connections:
            response = await llm.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=query)]
            )
            return _text(response.content), 0

        client = MultiServerMCPClient(connections)
        tools = await client.get_tools()
        if not tools:
            response = await llm.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=query)]
            )
            return _text(response.content), 0

        tool_map = {tool.name: tool for tool in tools}
        llm_with_tools = llm.bind_tools(tools, parallel_tool_calls=False)

        messages: list[Any] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query),
        ]
        tool_calls_count = 0

        for _ in range(max_turns):
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                return _text(response.content), tool_calls_count

            for call in tool_calls:
                tool_calls_count += 1
                tool_name = str(call.get("name", ""))
                tool = tool_map.get(tool_name)
                if tool is None:
                    result: Any = {"error": f"Tool not found: {tool_name}"}
                else:
                    try:
                        result = await tool.ainvoke(call.get("args", {}))
                    except Exception as exc:
                        result = {"error": str(exc)}

                if isinstance(result, str):
                    content = result
                else:
                    content = json.dumps(result, default=str)

                messages.append(ToolMessage(content=content, tool_call_id=str(call.get("id", ""))))

        return (
            "The specialist agent reached the tool-call turn limit before finishing.",
            tool_calls_count,
        )

    async def execute(
        self,
        *,
        query: str,
        preferred_agent_id: str | None = None,
    ) -> ExecuteResponse:
        definition = await self._select_agent(query, preferred_agent_id)
        llm = self._make_llm(definition.llm)
        max_turns = int(definition.llm.get("max_turns", self.settings.default_max_turns))

        answer, tool_calls = await self._run_with_tools(
            llm=llm,
            query=query,
            system_prompt=definition.system_prompt,
            mcp_servers=definition.mcp_servers,
            max_turns=max(1, min(max_turns, 12)),
        )

        return ExecuteResponse(
            agent_id=definition.id,
            agent_title=definition.title,
            score=definition.score,
            tool_calls=tool_calls,
            answer=answer,
        )
