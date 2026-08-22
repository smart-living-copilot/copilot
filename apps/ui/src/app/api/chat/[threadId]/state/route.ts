import { proxyWotbotJson } from '@/lib/wotbot-backend';

/**
 * Thread state used to seed `useStream`'s `initialValues`.
 *
 * A custom transport has no `fetchStateHistory`, so history is loaded here and
 * handed to the hook rather than fetched by it.
 */
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ threadId: string }> },
) {
  const { threadId } = await params;
  return proxyWotbotJson(`/threads/${encodeURIComponent(threadId)}/state`);
}
