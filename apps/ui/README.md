# UI

`ui` is the Next.js frontend for Smart Living Copilot. It owns the browser experience and keeps backend services behind server-side proxy routes.

## What This App Owns

- Chat and embedded chat experiences built around CopilotKit.
- Live mode controls for microphone, camera, agent dispatch, transcripts, and artifacts.
- Sidebar thread navigation, search, rename, and delete flows.
- Thing registry views for listing, creating, uploading, inspecting, and credential management.
- Automation job list, creation, detail, run history, conversation, and notification views.
- Settings screens for API key management.
- Server-side proxying to `copilot`, `code-executor`, and other internal service APIs.

The UI does not persist the active conversation itself. CopilotKit, the `chatId` route parameter, and the backend LangGraph checkpointer share the same thread identity.

## Runtime Shape

```text
browser
  -> Next.js UI
  -> server-side proxy routes
  -> copilot / code-executor
```

The browser talks to the Next.js app. The Next.js app forwards internal requests to backend services using environment-configured service URLs and shared internal credentials.

## Development

### With Docker Compose

```bash
docker compose up -d ui
docker compose exec ui npm run lint
docker compose exec ui npm run typecheck
docker compose exec ui npm run test
```

The dev override bind-mounts the app and preserves container-owned `node_modules` and `.next`.

### Directly

```bash
cd apps/ui
npm install
npm run dev
```

Use `npm run build` for a production build and `npm run start` to serve it.

## Version Label

The sidebar version label comes from `NEXT_PUBLIC_APP_VERSION` at build time. The publish workflow injects a release tag for tagged builds and the short commit SHA for branch builds. Local Docker builds can override it with:

```bash
APP_VERSION="$(git describe --tags --always --dirty)" docker compose up -d --build ui
```

## Environment

Most UI settings are backend URLs and shared internal credentials. See [`src/lib/backend-env.ts`](./src/lib/backend-env.ts), [`src/lib/app-version.ts`](./src/lib/app-version.ts), and the root [`.env.example`](../../.env.example).

### Embedded Chat

The embedded chat is available at `/embed/chat`. It creates an ephemeral chat session and cleans up best-effort when the page unloads.

The route supports initial prompt parameters:

```text
/embed/chat?prompt=Show%20the%20living%20room%20lights
/embed/chat?prompt=Show%20the%20living%20room%20lights&autosubmit=1
```

Add `jobEvents=0` to suppress the global job notification event stream
(`/api/jobs/events`) for embedded chat pages:

```text
/embed/chat?jobEvents=0
```

The disabled values are `0`, `false`, `no`, and `off`.

The route also accepts runtime prefill messages from its parent frame:

```ts
iframe.contentWindow?.postMessage(
  {
    type: 'deck:prefill',
    prompt: 'Show the living room lights',
    submit: true,
  },
  'https://ui.example',
);
```

Configure trusted parent origins with the runtime environment variable:

```bash
EMBED_CHAT_ALLOWED_ORIGINS=https://deck.example,http://localhost:8080
```

Only exact `http` and `https` origins are accepted. Wildcards, opaque `null` origins, invalid URLs, and non-HTTP protocols are ignored. The embed page is rendered dynamically, so this value is read at UI server runtime rather than at image build time.

## Important Files

- [`src/app`](./src/app): Next.js routes and server-side route handlers.
- [`src/components/copilot`](./src/components/copilot): chat, live mode, tool-call cards, and artifact rendering.
- [`src/components/jobs`](./src/components/jobs): automation job list, form, detail, run, and conversation UI.
- [`src/components/things`](./src/components/things): Thing registry screens and credential dialogs.
- [`src/components/settings`](./src/components/settings): settings panels.
- [`src/lib`](./src/lib): backend clients, stream helpers, deletion flow, formatters, and tests.
- [`src/hooks`](./src/hooks): browser-side hooks for job events and live media.

## Contributor Notes

- Keep backend service calls in server-side helpers or route handlers.
- Keep `chatId`, CopilotKit `threadId`, LangGraph `thread_id`, and code-executor session ids aligned.
- Keep Next.js route handlers thin; business logic belongs in shared libs or backend services.
- Preserve thread-delete cleanup across chat metadata, LangGraph state, and code-executor sessions.
- Prefer focused component tests around parsing, formatting, streaming, and cleanup behavior.
