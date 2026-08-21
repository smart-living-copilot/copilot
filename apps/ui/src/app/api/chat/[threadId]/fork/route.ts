import { proxyWotbotJson } from '@/lib/wotbot-backend';

/**
 * Rewinds a thread to just before a message, so an edit replaces the turn
 * instead of appending a second one beside it.
 */
export async function POST(
  req: Request,
  { params }: { params: Promise<{ threadId: string }> },
) {
  const { threadId } = await params;
  return proxyWotbotJson(`/threads/${encodeURIComponent(threadId)}/runs/fork`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: await req.text(),
  });
}
