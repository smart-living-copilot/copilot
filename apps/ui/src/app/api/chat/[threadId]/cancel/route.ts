import { proxyWotbotJson } from '@/lib/wotbot-backend';

/** Stops the in-flight backend run. Replaces the never-registered /ag-ui/stop. */
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
