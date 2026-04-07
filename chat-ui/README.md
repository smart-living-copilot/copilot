# Chat UI

`chat-ui` is the Next.js frontend for Smart Living Copilot. It renders the chat experience and proxies both CopilotKit runtime requests and thread APIs to the Python `copilot` service.

## What This App Owns

- Renders the main chat route with `CopilotKit` and `CopilotChat`.
- Uses the route param `chatId` as the real CopilotKit `threadId`.
- Creates, renames, deletes, filters, and groups sidebar threads.
- Proxies CopilotKit runtime requests from `/api/copilotkit` to the backend AG-UI endpoint.
- Proxies thread APIs from `/api/chats*` to `copilot`.

It does **not** own message persistence anymore. CopilotKit and the backend LangGraph checkpointer own the active conversation state.

## Current Chat Architecture

```text
/chat/[chatId]
  -> route-scoped CopilotKit provider
  -> CopilotChat
  -> /api/copilotkit
  -> LangGraphHttpAgent
  -> copilot /ag-ui
```

The sidebar uses `/api/chats` and `/api/chats/[chatId]` only as a thin proxy layer:

- `GET /api/chats`: list threads for the sidebar
- `POST /api/chats`: create a new thread id and placeholder title
- `GET /api/chats/[chatId]`: fetch one thread with metadata and messages
- `PATCH /api/chats/[chatId]`: rename a thread title
- `DELETE /api/chats/[chatId]`: trigger backend cleanup

Deleting a thread also fans out to:

- `code-executor /sessions/{chatId}`
- `copilot /threads/{chatId}`

## Important Files

- [`src/app/chat/[chatId]/page.tsx`](./src/app/chat/[chatId]/page.tsx): route-scoped `CopilotKit` provider and `CopilotChat`
- [`src/app/api/copilotkit/route.ts`](./src/app/api/copilotkit/route.ts): CopilotKit runtime bridge to `copilot /ag-ui`
- [`src/app/api/chats/route.ts`](./src/app/api/chats/route.ts): thread list/create proxy to `copilot /threads`
- [`src/app/api/chats/[chatId]/route.ts`](./src/app/api/chats/[chatId]/route.ts): thread read/rename proxy and delete cleanup fan-out
- [`src/components/chat-sidebar.tsx`](./src/components/chat-sidebar.tsx): thread picker, rename, search, grouping, optimistic delete
- [`src/lib/copilot-backend.ts`](./src/lib/copilot-backend.ts): shared proxy helper for internal backend requests
- [`src/app/providers.tsx`](./src/app/providers.tsx): theme, tooltip, and toast providers only

## Development Notes

### Version Label

The sidebar version label is no longer hard-coded in the UI.

- `chat-ui` reads `NEXT_PUBLIC_APP_VERSION` at build time when available.
- The publish workflow injects the git tag for tagged releases and the short commit SHA for branch builds.
- If no build metadata is provided, the UI shows `unknown`.
- For local Docker dev, you can rebuild with `APP_VERSION="$(git describe --tags --always --dirty)" docker compose up -d --build chat-ui`.

### With Docker Compose

```bash
docker compose up -d chat-ui
docker compose exec chat-ui npm run lint
docker compose exec chat-ui npm run typecheck
```

### Hot Reload Caveat

The dev override bind-mounts `src/` and `public/`, but not `package.json`.

That means:

- source changes hot-reload
- dependency or script changes need a rebuild

Use:

```bash
docker compose up -d --build chat-ui
```

## Contributor Rules Of Thumb

- Keep CopilotKit as the source of truth for the active conversation.
- Keep `/api/chats` lightweight. It should stay a thin proxy to backend thread APIs, not a second chat system.
- If a feature needs real conversation history or metadata, prefer the backend thread/checkpoint model over local frontend persistence.
- Keep `chatId` and CopilotKit `threadId` aligned.
- When deleting a thread, preserve the current fan-out cleanup behavior unless the backend contract changes.
