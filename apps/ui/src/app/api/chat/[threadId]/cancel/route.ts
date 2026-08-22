import { proxyWotbotJson } from '@/lib/wotbot-backend';

/** Stops the in-flight backend run for this thread. */
export async function POST(
  _req: Request,
  { params }: { params: Promise<{ threadId: string }> },
) {
  const { threadId } = await params;
  return proxyWotbotJson(
    `/threads/${encodeURIComponent(threadId)}/runs/cancel`,
    { method: 'POST' },
  );
}
