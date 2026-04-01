# Smart Living Copilot

Smart Living Copilot is a multi-service smart home assistant stack. This repository contains the chat frontend, the Python copilot service, the code execution service used for analysis workflows, and local data replay tooling for development.

## Services

```text
browser
  -> chat-ui
  -> copilot
  -> code-executor
  -> wot-registry / wot-runtime

optional local fixture source:
  data-replay
```

- [`chat-ui`](./chat-ui/README.md): Next.js frontend, chat UX, sidebar thread index, and internal API proxying.
- [`copilot`](./copilot/README.md): FastAPI + LangGraph agent service behind the chat experience.
- [`code-executor`](./code-executor/README.md): internal Python execution service used by `run_code`.
- [`data-replay`](./data-replay/README.md): local replay server for offline device history fixtures.
- [`thing_descriptions`](./thing_descriptions): local Thing Description assets used for integration and replay scenarios.

## Getting Started

1. Copy [`.env.example`](./.env.example) to `.env` and fill in the required values.
2. Start the stack with Docker Compose:

```bash
docker compose up -d
```

3. Open `http://localhost:3000`.

For local development, [docker-compose.override.yaml](./docker-compose.override.yaml) is picked up automatically by `docker compose` and enables live-reload setups for the main services.

## Documentation

- [Chat UI README](./chat-ui/README.md)
- [Copilot README](./copilot/README.md)
- [Code Executor README](./code-executor/README.md)
- [Data Replay README](./data-replay/README.md)

## Top-Level Files

- [`docker-compose.yaml`](./docker-compose.yaml): default multi-service stack definition.
- [`docker-compose.override.yaml`](./docker-compose.override.yaml): local development overrides.
- [`LICENSE`](./LICENSE): project license.

