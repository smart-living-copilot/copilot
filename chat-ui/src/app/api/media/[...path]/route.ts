import { fetchCopilot } from '@/lib/copilot-backend';

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxyMediaRequest(req: Request, context: RouteContext) {
  const { path } = await context.params;
  const targetPath = `/media/${path.map(encodeURIComponent).join('/')}`;
  const body =
    req.method === 'GET' || req.method === 'HEAD'
      ? undefined
      : await req.text();

  let response: Response;
  try {
    response = await fetchCopilot(targetPath, {
      method: req.method,
      headers: {
        'Content-Type': req.headers.get('content-type') || 'application/json',
      },
      body,
      // Tie the upstream connection to the client request so that closing the
      // EventSource (or any other client disconnect) cancels the backend call.
      signal: req.signal,
    });
  } catch (error) {
    if (req.signal.aborted) {
      // Client went away while we were waiting for the upstream — no body to send.
      return new Response(null, { status: 499 });
    }
    return Response.json(
      {
        detail:
          error instanceof Error
            ? error.message
            : 'Media backend request failed',
      },
      { status: 502 },
    );
  }

  const contentType =
    response.headers.get('content-type') || 'application/json';

  if (contentType.includes('text/event-stream')) {
    return new Response(response.body, {
      status: response.status,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'no-cache, no-transform',
        'X-Accel-Buffering': 'no',
        Connection: 'keep-alive',
      },
    });
  }

  return new Response(response.body, {
    status: response.status,
    headers: { 'Content-Type': contentType },
  });
}

export async function GET(req: Request, context: RouteContext) {
  return proxyMediaRequest(req, context);
}

export async function POST(req: Request, context: RouteContext) {
  return proxyMediaRequest(req, context);
}

export async function DELETE(req: Request, context: RouteContext) {
  return proxyMediaRequest(req, context);
}
