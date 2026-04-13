# Specialist Agent Runtime

`specialist-agent` is a separate service that discovers specialist agents from Thing Descriptions and executes the best match for a query.

## How It Works

1. Reads candidate Thing Descriptions from `wot-registry` (`/api/things`).
2. Filters to agent-like TDs (`tags: ["agent"]`, `@type: "Agent"`, or `x-copilot-agent`).
3. Picks the best match for the query.
4. Builds an LLM session from TD config and optionally loads TD-defined MCP servers.
5. Returns the specialist answer to the caller (`copilot`).

## TD Extension Contract

Put specialist runtime config under `x-copilot-agent` (or `x-agent`) in the Thing Description.

```json
{
  "id": "energy-specialist",
  "title": "Energy Specialist",
  "tags": ["agent", "energy", "analytics"],
  "description": "Specialist for power and energy analysis.",
  "@type": "Agent",
  "x-copilot-agent": {
    "systemPrompt": "You are an energy analytics specialist...",
    "llm": {
      "model": "gpt-4o-mini",
      "temperature": 0.1,
      "max_turns": 6
    },
    "mcpServers": [
      {
        "name": "registry",
        "transport": "streamable_http",
        "url": "http://wot-registry:8000/mcp",
        "headers": {
          "Authorization": "Bearer <token>"
        }
      }
    ]
  }
}
```

## Endpoints

- `GET /health`
- `POST /agents/prepare-mcps`
- `GET /agents/search?q=...`
- `POST /agents/execute`

All non-health endpoints require `Authorization: Bearer <INTERNAL_API_KEY>` when configured.

## Docker MCP Gateway Integration

This stack can run `docker/mcp-gateway` so specialist agents can dynamically discover and enable MCP servers.

In a specialist TD, add the gateway as one MCP server:

```json
{
  "name": "docker_gateway",
  "transport": "streamable_http",
  "url": "http://docker-mcp-gateway:8811/mcp"
}
```

When Docker's `dynamic-tools` feature is enabled, the gateway exposes management tools such as `mcp-find` and `mcp-add` so a specialist can search and spawn servers at runtime.

On the Docker host, enable it once:

```bash
docker mcp feature enable dynamic-tools
```

Important: do not pass `--servers=...` to gateway when you want dynamic tools. Explicit `--servers` mode disables dynamic server management tools.
