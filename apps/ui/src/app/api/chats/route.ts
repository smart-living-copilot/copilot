import { getCodeExecutorUrl, getWotbotUrl } from '@/lib/backend-env';
import {
  cleanupChatResourcesBatch,
  selectChatsForBatchDeletion,
  type ChatBatchDeleteRequest,
  type ChatDeletionCandidate,
} from '@/lib/chat-deletion';
import { fetchWotbot, proxyWotbotJson } from '@/lib/wotbot-backend';

export async function GET() {
  return proxyWotbotJson('/threads');
}

export async function POST() {
  return proxyWotbotJson('/threads', { method: 'POST' });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function parseBatchDeleteRequest(
  body: unknown,
): ChatBatchDeleteRequest | Response {
  if (!isRecord(body)) {
    return Response.json(
      { detail: 'Request body is required' },
      { status: 400 },
    );
  }

  if (body.mode === 'all') {
    return { mode: 'all' };
  }

  if (body.mode === 'before') {
    if (
      typeof body.before !== 'string' ||
      Number.isNaN(Date.parse(body.before))
    ) {
      return Response.json(
        { detail: 'A valid before date is required' },
        { status: 400 },
      );
    }

    return { mode: 'before', before: body.before };
  }

  return Response.json(
    { detail: 'Unsupported chat deletion mode' },
    { status: 400 },
  );
}

export async function DELETE(req: Request) {
  const request = parseBatchDeleteRequest(
    await req.json().catch(() => undefined),
  );

  if (request instanceof Response) {
    return request;
  }

  const chatsResponse = await fetchWotbot('/threads');
  if (!chatsResponse.ok) {
    return Response.json(
      { detail: 'Could not load chats for deletion' },
      { status: chatsResponse.status },
    );
  }

  const chats = (await chatsResponse.json().catch(() => null)) as
    | ChatDeletionCandidate[]
    | null;

  if (!Array.isArray(chats)) {
    return Response.json(
      { detail: 'Could not read chats for deletion' },
      { status: 502 },
    );
  }

  const targets = selectChatsForBatchDeletion(chats, request);
  const chatIds = targets
    .map((chat) => chat.id)
    .filter(
      (chatId): chatId is string =>
        typeof chatId === 'string' && chatId.trim().length > 0,
    );
  const results = await cleanupChatResourcesBatch({
    chatIds,
    wotbotUrl: getWotbotUrl(),
    executorUrl: getCodeExecutorUrl(),
    internalApiKey: process.env.INTERNAL_API_KEY,
  });
  const failures = results.filter((result) => result.failures.length > 0);

  if (failures.length) {
    return Response.json(
      {
        detail: 'Failed to fully delete all selected chats',
        requested: chatIds.length,
        deleted: results.length - failures.length,
        failures,
      },
      { status: 502 },
    );
  }

  return Response.json({
    ok: true,
    deleted: chatIds.length,
    chatIds,
  });
}
