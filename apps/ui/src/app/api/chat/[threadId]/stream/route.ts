import { fetchWotbot } from '@/lib/wotbot-backend';

/**
 * Pass-through for the LangGraph run stream.
 *
 * Deliberately dumb: it pipes the upstream body through untouched so the SSE
 * frames reach `useStream` exactly as the backend wrote them. It exists only to
 * keep INTERNAL_API_KEY server-side -- it does not parse, buffer, reorder, or
 * synthesize events, which is what the CopilotKit runtime it replaces did.
 */
export async function POST(
  req: Request,
  { params }: { params: Promise<{ threadId: string }> },
) {
  const { threadId } = await params;
  const body = await req.text();

  const upstream = await fetchWotbot(
    `/threads/${encodeURIComponent(threadId)}/runs/stream`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      signal: req.signal,
      // Streaming responses must not be buffered by fetch's cache layer.
      cache: 'no-store',
    },
  );

  if (!upstream.ok || !upstream.body) {
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        'Content-Type':
          upstream.headers.get('content-type') || 'application/json',
      },
    });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      // Stops nginx-style proxies from buffering the stream into silence.
      'X-Accel-Buffering': 'no',
    },
  });
}
