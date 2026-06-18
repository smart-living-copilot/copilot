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

### Generated contract types

The copilot↔servient wire shape has a single source of truth: copilot's `VirtualThingServientView` Pydantic model. The committed `schema/servient-view.schema.json` and `src/types.generated.ts` are derived from it, so `npm run build` and the tests need no extra step.

Regenerate them after changing the model:

```bash
npm run gen:types      # exports the schema from copilot, then regenerates the TS
npm run check:contract # regenerates and fails (git diff) if anything is stale
```

`gen:types` runs copilot's `python -m copilot.virtual_things.contract_export`, so it requires copilot's Python venv on `PATH` (e.g. `PATH="../copilot/.venv/bin:$PATH" npm run gen:types`). Wire `check:contract` into CI to catch drift. Do not hand-edit `src/types.generated.ts`.

## Environment

The Docker image defaults to:

- `REGISTRY_URL=http://copilot:8123`
- `REDIS_URL=redis://valkey:6379`
- `PORT=3013`
- `WOT_PORT=3014`
- `VIRTUAL_SERVIENT_PUBLIC_URL=http://virtual-servient:3014`
- `VIRTUAL_SERVIENT_EVENTS_GROUP=virtual_servient`
- `VIRTUAL_SERVIENT_RECONCILE_INTERVAL_MS=30000`

Compose also sets `VIRTUAL_SERVIENT_REGISTRY_TOKEN` from the root environment. See [`src/config.ts`](./src/config.ts) and the root [`.env.example`](../../.env.example).

## Important Files

- [`src/index.ts`](./src/index.ts): service startup and health routes.
- [`src/config.ts`](./src/config.ts): environment parsing.
- [`src/manager.ts`](./src/manager.ts): definition reconciliation, production lifecycle, and event emission.
- [`src/td.ts`](./src/td.ts): concrete Thing Description/form generation.
- [`src/triggers.ts`](./src/triggers.ts): interval and source-event trigger setup.
- [`src/types.ts`](./src/types.ts): runtime type aliases over the generated contract (`ThingDescription` plus re-exports of `src/types.generated.ts`).
- [`src/types.generated.ts`](./src/types.generated.ts): generated definition-view types (do not edit; see [Generated contract types](#generated-contract-types)).
- [`src/events.ts`](./src/events.ts): Redis stream consumer for definition and emission events.
- [`src/servient.ts`](./src/servient.ts): node-wot servient setup.
- [`src/clients/copilot.ts`](./src/clients/copilot.ts): internal copilot API client.
- [`src/redis.ts`](./src/redis.ts): shared Redis client.

## Contributor Notes

- Keep definition persistence and handler execution in `copilot`; this service should stay focused on producing WoT Things.
- Keep virtual record Things on the generic virtual Thing path, not a separate runtime shortcut.
- Prefer adding event trigger behavior in `manager.ts` and reusing the existing `thing_events` stream for cross-process delivery.
