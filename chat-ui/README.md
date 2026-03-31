# Chat UI

`chat-ui` is the Next.js frontend for Smart Living Copilot. It renders the chat experience, keeps a lightweight thread index for the sidebar, and proxies CopilotKit runtime requests to the Python `copilot` service.

## What This App Owns

- Renders the main chat route with `CopilotKit` and `CopilotChat`.
- Uses the route param `chatId` as the real CopilotKit `threadId`.
- Stores only sidebar thread metadata locally: `id`, `title`, `createdAt`, `updatedAt`.
- Creates, renames, deletes, filters, and groups sidebar threads.
- Proxies CopilotKit runtime requests from `/api/copilotkit` to the backend AG-UI endpoint.

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

The sidebar uses `/api/chats` and `/api/chats/[chatId]` only as a thread index:

- `GET /api/chats`: list threads for the sidebar
- `POST /api/chats`: create a new thread id and placeholder title
- `PATCH /api/chats/[chatId]`: rename a thread title
- `DELETE /api/chats/[chatId]`: remove the sidebar row and trigger backend cleanup

Deleting a thread also fans out to:

- `code-executor /sessions/{chatId}`
- `copilot /threads/{chatId}`

## Important Files

- [`src/app/chat/[chatId]/page.tsx`](./src/app/chat/[chatId]/page.tsx): route-scoped `CopilotKit` provider and `CopilotChat`
- [`src/app/api/copilotkit/route.ts`](./src/app/api/copilotkit/route.ts): CopilotKit runtime bridge to `copilot /ag-ui`
- [`src/app/api/chats/route.ts`](./src/app/api/chats/route.ts): list/create sidebar threads
- [`src/app/api/chats/[chatId]/route.ts`](./src/app/api/chats/[chatId]/route.ts): rename/delete sidebar threads and trigger cleanup
- [`src/components/chat-sidebar.tsx`](./src/components/chat-sidebar.tsx): thread picker, rename, search, grouping, optimistic delete
- [`src/db/schema.ts`](./src/db/schema.ts): local SQLite thread index schema
- [`src/app/providers.tsx`](./src/app/providers.tsx): theme, tooltip, and toast providers only

## Local Storage Model

The local SQLite table is intentionally small:

```ts
chats: {
  id: string;
  title: string;
  createdAt: Date;
  updatedAt: Date;
}
```

This table exists to make the sidebar nice to use. It is not the source of truth for message history.

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
- Keep `/api/chats` lightweight. It should stay a sidebar-thread index, not a second chat system.
- If a feature needs real conversation history, prefer the backend thread/checkpoint model over local SQLite.
- Keep `chatId` and CopilotKit `threadId` aligned.
- When deleting a thread, preserve the current fan-out cleanup behavior unless the backend contract changes.
