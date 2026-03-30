export function buildInternalHeaders(internalApiKey?: string) {
  if (!internalApiKey) {
    return undefined;
  }

  return {
    Authorization: `Bearer ${internalApiKey}`,
  };
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
  copilotUrl,
  executorUrl,
  fetchImpl,
  internalApiKey,
}: {
  chatId: string;
  copilotUrl?: string;
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

  if (copilotUrl) {
    cleanupResults.push(
      deleteRemoteResource(
        `${copilotUrl}/threads/${encodeURIComponent(chatId)}`,
        headers,
        'Copilot thread',
        fetchImpl,
      ),
    );
  }

  const failures = await Promise.all(cleanupResults);
  return failures.filter((value): value is string => Boolean(value));
}
