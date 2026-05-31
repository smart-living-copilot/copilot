# Smart Living Copilot

Smart Living Copilot is a multi-service smart home assistant stack. This repository contains the chat frontend, the Python copilot service, and the code execution service used for analysis workflows.

## Services

```text
browser
  -> ui
  -> copilot
  -> code-executor
  -> wot-runtime
```

- [`apps/ui`](./apps/ui/README.md): Next.js frontend, chat UX, sidebar thread index, and internal API proxying.
- [`apps/copilot`](./apps/copilot/README.md): FastAPI + LangGraph agent service behind the chat experience.
- [`apps/code-executor`](./apps/code-executor/README.md): internal Python execution service used by `run_code`.
- [`examples/thing-descriptions`](./examples/thing-descriptions): local Thing Description assets used for integration scenarios.

## Getting Started

1. Copy [`.env.example`](./.env.example) to `.env` and fill in the required values.
2. Start the stack with Docker Compose:

```bash
docker compose up -d
```

3. Open `http://localhost:3000`.

For local development, [docker-compose.override.yaml](./docker-compose.override.yaml) is picked up automatically by `docker compose` and includes the canonical override in [`deploy/compose.override.yaml`](./deploy/compose.override.yaml).

## Documentation

- [UI README](./apps/ui/README.md)
- [Copilot README](./apps/copilot/README.md)
- [Code Executor README](./apps/code-executor/README.md)

## Top-Level Files

- [`docker-compose.yaml`](./docker-compose.yaml): root compatibility wrapper for the default stack.
- [`docker-compose.override.yaml`](./docker-compose.override.yaml): root compatibility wrapper for local development overrides.
- [`deploy/compose.yaml`](./deploy/compose.yaml): canonical multi-service stack definition.
- [`LICENSE`](./LICENSE): project license.
