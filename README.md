# WoTBot

WoTBot is a multi-service Web of Things assistant stack. It combines a Next.js chat and operations UI, a Python LangGraph WoTBot service, a Python code execution service, a node-wot runtime for Web of Things device access, and a virtual Thing producer for computed and record-backed Things.

## Services

```text
browser
  -> ui
  -> wotbot
     -> code-executor
     -> wot-runtime
     -> virtual-servient
     -> postgres / valkey
```

- [`apps/ui`](./apps/ui/README.md): Next.js frontend for chat, live mode, Things, jobs, settings, and backend proxying.
- [`apps/wotbot`](./apps/wotbot/README.md): FastAPI + LangGraph service for agent orchestration, Thing registry APIs, jobs, persistence, and LiveKit worker roles.
- [`apps/code-executor`](./apps/code-executor/README.md): internal Python worker service used by the agent's `run_code` tool.
- [`apps/wot-runtime`](./apps/wot-runtime/README.md): internal node-wot runtime that reads, writes, invokes, and subscribes against Thing Descriptions.
- [`apps/virtual-servient`](./apps/virtual-servient/README.md): internal node-wot producer that turns wotbot virtual Thing definitions into concrete catalog Thing Descriptions.
- [`examples/thing-descriptions`](./examples/thing-descriptions): sample Thing Description assets for local scenarios.

Docker Compose also starts Postgres with pgvector, Valkey, an RDF service, and LiveKit Server.

## Getting Started

1. Copy [`.env.example`](./.env.example) to `.env`.
2. Fill the required LLM and shared-secret values.
3. Start the stack:

```bash
docker compose up -d
```

4. Open `http://localhost:3000`.

The root Compose files are compatibility wrappers around the canonical stack in [`deploy/compose.yaml`](./deploy/compose.yaml) and its local development override in [`deploy/compose.override.yaml`](./deploy/compose.override.yaml).

## Agent-to-Agent (A2A) Integration

WoTBot exposes a lightweight A2A HTTP surface so other agents can discover
and send short messages into the agent runtime.

- `GET /api/a2a/agent-card` — returns a small JSON "agent card" describing
  the agent and the A2A inbox.
- `POST /api/a2a/message` — send a short message to be executed by the
  WoTBot AG-UI runtime. The request body should be `{ "message": "..." }`.

When running via the provided Docker Compose (`deploy/compose.yaml`) the
API is published on the host at `http://localhost:8123` (the Compose file
maps the container port `8123` to the host). Example:

```bash
# Agent discovery
curl http://localhost:8123/api/a2a/agent-card

# Send a message (requires the configured internal API key in Authorization header)
curl -X POST http://localhost:8123/api/a2a/message \
  -H "Authorization: Bearer <INTERNAL_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello from other-agent"}'
```

Note: `POST /api/a2a/message` is a convenience endpoint that runs the message
via the AG-UI runtime and returns the run events. For richer streaming (SSE)
use the `/ag-ui` endpoint.

## EDC Dataspace Integration

WoTBot can interact with Eclipse Dataspace Components (EDC) connectors to
discover, negotiate, and download datasets from a dataspace. The integration
is driven by Thing Descriptions — an EDC consumer portal is registered as a
Thing whose actions (queryCatalog, negotiateContract, initiateTransfer, etc.)
map to the EDC Management API.

### Thing Description structure

The EDC consumer portal Thing (`urn:smart-living:dataspace:edc-consumer`)
exposes the full dataspace lifecycle:

1. **Discover** — `searchFederatedCatalog` / `queryCatalog` to find datasets
2. **Negotiate** — `negotiateContract` with an ODRL policy, poll `contractNegotiation`
3. **Transfer** — `initiateTransfer` (HttpData-PULL), get EDR via `edrDataAddress`
4. **Download** — `downloadAsset` with the EDR endpoint and authorization token

The `downloadAsset` action is special-cased in the wot-runtime: it makes a
direct HTTP GET request with the EDR bearer token, bypassing node-wot's
GET-without-body limitation. The authorization value is the raw JWT from the
EDR (without a `"Bearer "` prefix).


## MCP (Model Context Protocol) Integration

WoTBot supports MCP servers as first-class Things. Any MCP server with a
Streamable HTTP transport can be registered as a Thing Description whose
actions have `mcp:tool` form bindings. The wot-runtime transparently routes
`wot_invoke_action` calls through JSON-RPC 2.0 to the MCP server.

### Architecture

```
Agent: wot_invoke_action("urn:edc:mcp:tx-consumer-portal", "get_catalog", {...})
  │
  ▼
wot-runtime → detects "mcp:tool" in the form → JSON-RPC 2.0 call
  │
  ├─ POST {jsonrpc:"2.0", method:"tools/call", params:{name:"<tool>", arguments:{...}}}
  │   to the MCP server endpoint
  │
  ▼
MCP Server → returns SSE response → runtime extracts content → agent
```

### Session management

The wot-runtime automatically manages MCP sessions:

1. **`ensureMcpSession()`** — sends `initialize` JSON-RPC call, caches the
   `mcp-session-id` header value per endpoint
2. **`mcpCall()`** — sends `tools/call` with the session ID, handles SSE
   (`event: message` / `data: {...}`) responses
3. **202 Accepted** — if the server returns 202 (Streamable HTTP), the
   runtime polls via GET to retrieve the result
4. Sessions are reused across multiple tool calls within the same runtime
   lifetime

### Thing Description format

Add an MCP server to the catalog by creating a Thing Description with
`mcp:tool` on each action form:

```json
{
  "@context": [
    "https://www.w3.org/2022/wot/td/v1.1",
    { "mcp": "https://modelcontextprotocol.io/specification/2025-03-26#" }
  ],
  "id": "urn:mcp:my-server",
  "title": "My MCP Server",
  "actions": {
    "my_tool": {
      "title": "My Tool",
      "input": { "type": "object", "properties": { ... } },
      "forms": [{
        "href": "http://mcp-server:8081/mcp",
        "contentType": "application/json",
        "op": ["invokeaction"],
        "mcp:tool": "my_tool"
      }]
    }
  }
}
```


## Development

The default local setup uses Docker Compose with bind mounts and hot reload where practical:

```bash
docker compose up -d --build
```

Service-specific setup, test commands, and implementation notes live in the service READMEs:

- [UI README](./apps/ui/README.md)
- [WoTBot README](./apps/wotbot/README.md)
- [Code Executor README](./apps/code-executor/README.md)
- [WoT Runtime README](./apps/wot-runtime/README.md)
- [Virtual Servient README](./apps/virtual-servient/README.md)

## Versioning

The stack uses one shared version in [`VERSION`](./VERSION). Update every service
manifest from that source of truth with:

```bash
scripts/set-version.sh 0.1.0
scripts/check-version.sh
```

Release tags should be `v<version>` (for example `v0.1.0`). CI runs the version
check before building images and rejects tag/version drift.

## Top-Level Files

- [`docker-compose.yaml`](./docker-compose.yaml): root wrapper for the default stack.
- [`docker-compose.override.yaml`](./docker-compose.override.yaml): root wrapper for local development overrides.
- [`deploy/compose.yaml`](./deploy/compose.yaml): canonical multi-service stack definition.
- [`.env.example`](./.env.example): documented environment template.
- [`VERSION`](./VERSION): shared stack version used by all service manifests.
- [`LICENSE`](./LICENSE): project license.
