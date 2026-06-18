# Smart Living Copilot

Smart Living Copilot is a multi-service smart home assistant stack. It combines a Next.js chat and operations UI, a Python LangGraph copilot service, a Python code execution service, a node-wot runtime for Web of Things device access, and a virtual Thing producer for computed and record-backed Things.

## Services

```text
browser
  -> ui
  -> copilot
     -> code-executor
     -> wot-runtime
     -> virtual-servient
     -> postgres / valkey
```

- [`apps/ui`](./apps/ui/README.md): Next.js frontend for chat, live mode, Things, jobs, settings, and backend proxying.
- [`apps/copilot`](./apps/copilot/README.md): FastAPI + LangGraph service for agent orchestration, Thing registry APIs, jobs, persistence, and LiveKit worker roles.
- [`apps/code-executor`](./apps/code-executor/README.md): internal Python worker service used by the agent's `run_code` tool.
- [`apps/wot-runtime`](./apps/wot-runtime/README.md): internal node-wot runtime that reads, writes, invokes, and subscribes against Thing Descriptions.
- [`apps/virtual-servient`](./apps/virtual-servient/README.md): internal node-wot producer that turns copilot virtual Thing definitions into concrete catalog Thing Descriptions.
- [`examples/thing-descriptions`](./examples/thing-descriptions): sample Thing Description assets for local scenarios.

Docker Compose also starts Postgres with pgvector, Valkey, an RDF service, LiveKit Server, and an optional Kokoro TTS profile.

## Getting Started

1. Copy [`.env.example`](./.env.example) to `.env`.
2. Fill the required LLM and shared-secret values.
3. Start the stack:

```bash
docker compose up -d
```

4. Open `http://localhost:3000`.

The root Compose files are compatibility wrappers around the canonical stack in [`deploy/compose.yaml`](./deploy/compose.yaml) and its local development override in [`deploy/compose.override.yaml`](./deploy/compose.override.yaml).

## Development

The default local setup uses Docker Compose with bind mounts and hot reload where practical:

```bash
docker compose up -d --build
```

Service-specific setup, test commands, and implementation notes live in the service READMEs:

- [UI README](./apps/ui/README.md)
- [Copilot README](./apps/copilot/README.md)
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
