export function buildInternalHeaders(internalApiKey?: string) {
  if (!internalApiKey) {
    return undefined;
  }

  return {
    Authorization: `Bearer ${internalApiKey}`,
  };
}

export interface ChatDeletionCandidate {
  id: string;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export type ChatBatchDeleteRequest =
  | { mode: 'all' }
  | { mode: 'before'; before: string };

export interface ChatCleanupResult {
  chatId: string;
  failures: string[];
}

function getChatDeletionTime(chat: ChatDeletionCandidate) {
  const updatedTime = chat.updatedAt ? Date.parse(chat.updatedAt) : Number.NaN;
  if (Number.isFinite(updatedTime)) {
    return updatedTime;
  }

  const createdTime = chat.createdAt ? Date.parse(chat.createdAt) : Number.NaN;
  return Number.isFinite(createdTime) ? createdTime : null;
}

export function selectChatsForBatchDeletion(
  chats: ChatDeletionCandidate[],
  request: ChatBatchDeleteRequest,
) {
  if (request.mode === 'all') {
    return chats;
  }

  const cutoffTime = Date.parse(request.before);
  if (!Number.isFinite(cutoffTime)) {
    return [];
  }

  return chats.filter((chat) => {
    const chatTime = getChatDeletionTime(chat);
    return chatTime !== null && chatTime <= cutoffTime;
  });
}

export async function deleteRemoteResource(
  url: string,
  headers: HeadersInit | undefined,
  label: string,
  fetchImpl: typeof fetch = fetch,
) {
  try {
    const response = await fetchImpl(url, {
      method: 'DELETE',
      headers,
    });

    if (response.ok || response.status === 404) {
      return null;
    }

    return `${label} cleanup failed (${response.status})`;
  } catch {
    return `${label} cleanup failed`;
  }
}

export async function cleanupChatResources({
  chatId,
  wotbotUrl,
  executorUrl,
  fetchImpl,
  internalApiKey,
}: {
  chatId: string;
  wotbotUrl?: string;
  executorUrl?: string;
  fetchImpl?: typeof fetch;
  internalApiKey?: string;
}) {
  const headers = buildInternalHeaders(internalApiKey);
  const cleanupResults: Array<Promise<string | null>> = [];

  if (executorUrl) {
    cleanupResults.push(
      deleteRemoteResource(
        `${executorUrl}/sessions/${chatId}`,
        headers,
        'Code executor session',
        fetchImpl,
      ),
    );
  }

  if (wotbotUrl) {
    cleanupResults.push(
      deleteRemoteResource(
        `${wotbotUrl}/threads/${encodeURIComponent(chatId)}`,
        headers,
        'WoTBot thread',
        fetchImpl,
      ),
    );
  }

  const failures = await Promise.all(cleanupResults);
  return failures.filter((value): value is string => Boolean(value));
}

export async function cleanupChatResourcesBatch({
  chatIds,
  wotbotUrl,
  executorUrl,
  fetchImpl,
  internalApiKey,
}: {
  chatIds: string[];
  wotbotUrl?: string;
  executorUrl?: string;
  fetchImpl?: typeof fetch;
  internalApiKey?: string;
}): Promise<ChatCleanupResult[]> {
  return Promise.all(
    chatIds.map(async (chatId) => ({
      chatId,
      failures: await cleanupChatResources({
        chatId,
        wotbotUrl,
        executorUrl,
        fetchImpl,
        internalApiKey,
      }),
    })),
  );
}
