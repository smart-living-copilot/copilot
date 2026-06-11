# Virtual Servient

`virtual-servient` is the internal Node.js service that produces Smart Living Copilot Virtual Things as concrete Web of Things Things. It watches virtual Thing definitions stored by `copilot`, exposes them through node-wot, and registers the produced Thing Descriptions back into the catalog.

## What This Service Owns

- Producing standalone and record-backed virtual Things through node-wot.
- Concrete HTTP forms for virtual properties, actions, and events.
- Event trigger loops for interval and source-event emitted bindings.
- Explicit virtual event emission from copilot's Thing event stream.
- Catalog registration and cleanup for produced virtual Thing TDs.

It does not own virtual Thing definitions, handler code, or record persistence. `copilot` remains the source of truth for definitions, bindings, handler execution, job records, and catalog storage.

## Runtime Shape

```text
copilot VirtualThingStore
  -> Redis thing_events stream
  -> virtual-servient
     -> node-wot producer servient
     -> concrete virtual Thing TDs in copilot catalog
     -> wot-runtime consumes them like normal Things
```

Property reads and action invocations call back into `copilot`'s virtual Thing dispatcher. Emitted events are evaluated by `copilot`; this service owns the live WoT event emission on the produced Thing.

## Development

### With Docker Compose

```bash
docker compose up -d virtual-servient
```

The dev override builds the local service, bind-mounts the app, and runs `tsx watch`.

### Directly

```bash
cd apps/virtual-servient
npm install
npm run dev
```

Use `npm run build` for TypeScript compilation, `npm run test` for unit tests, and `npm run lint` for ESLint.

## Environment

The Docker image defaults to:

- `REGISTRY_URL=http://copilot:8123`
- `REDIS_URL=redis://valkey:6379`
- `PORT=3013`
- `WOT_PORT=3014`
- `VIRTUAL_SERVIENT_PUBLIC_URL=http://virtual-servient:3014`

Compose also sets `VIRTUAL_SERVIENT_REGISTRY_TOKEN` from the root environment. See [`src/config.ts`](./src/config.ts) and the root [`.env.example`](../../.env.example).

## Important Files

- [`src/index.ts`](./src/index.ts): service startup and health routes.
- [`src/config.ts`](./src/config.ts): environment parsing.
- [`src/manager.ts`](./src/manager.ts): definition reconciliation, production, triggers, and event emission.
- [`src/events.ts`](./src/events.ts): Redis stream consumer for definition and emission events.
- [`src/servient.ts`](./src/servient.ts): node-wot servient setup.
- [`src/clients/copilot.ts`](./src/clients/copilot.ts): internal copilot API client.
- [`src/redis.ts`](./src/redis.ts): shared Redis client.

## Contributor Notes

- Keep definition persistence and handler execution in `copilot`; this service should stay focused on producing WoT Things.
- Keep virtual record Things on the generic virtual Thing path, not a separate runtime shortcut.
- Prefer adding event trigger behavior in `manager.ts` and reusing the existing `thing_events` stream for cross-process delivery.
