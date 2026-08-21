export const LIVE_MODE_SETTLE_DELAYS_MS = [0, 300, 700] as const;
export const RUN_RECOVERY_DELAYS_MS = [100, 250, 500] as const;

type Fetcher = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;
type Wait = (delayMs: number) => Promise<void>;

const waitFor = (delayMs: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, delayMs));

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Fetches one authoritative checkpoint snapshot through the local proxy. */
export async function fetchThreadState<TState extends Record<string, unknown>>(
  threadId: string,
  fetcher: Fetcher = fetch,
): Promise<TState> {
  const response = await fetcher(
    `/api/chat/${encodeURIComponent(threadId)}/state`,
  );
  if (!response.ok) {
    throw new Error(`Could not load conversation (${response.status})`);
  }

  const data: unknown = await response.json();
  if (!isRecord(data) || !isRecord(data.values)) {
    throw new Error('Conversation state response was invalid');
  }
  return data.values as TState;
}

/**
 * Re-reads a thread over a bounded interval and returns the newest successful
 * snapshot. Multiple reads cover checkpoint writes that finish just after a
 * failed/cancelled run or a LiveKit room disconnects.
 */
export async function loadSettledThreadState<
  TState extends Record<string, unknown>,
>(
  threadId: string,
  {
    delaysMs = [0],
    fetcher = fetch,
    wait = waitFor,
  }: {
    delaysMs?: readonly number[];
    fetcher?: Fetcher;
    wait?: Wait;
  } = {},
): Promise<TState> {
  let latest: TState | null = null;
  let lastError: unknown = null;

  for (const delayMs of delaysMs.length ? delaysMs : [0]) {
    if (delayMs > 0) {
      await wait(delayMs);
    }
    try {
      latest = await fetchThreadState<TState>(threadId, fetcher);
    } catch (error) {
      lastError = error;
    }
  }

  if (latest) {
    return latest;
  }
  throw lastError instanceof Error
    ? lastError
    : new Error('Could not load conversation');
}
