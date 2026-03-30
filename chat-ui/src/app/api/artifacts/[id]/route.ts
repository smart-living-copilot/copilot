export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const executorUrl =
    process.env.CODE_EXECUTOR_URL || 'http://code-executor:8888';
  const internalApiKey = process.env.INTERNAL_API_KEY || '';

  const res = await fetch(
    `${executorUrl}/artifacts/${encodeURIComponent(id)}`,
    {
      headers: {
        ...(internalApiKey
          ? { Authorization: `Bearer ${internalApiKey}` }
          : {}),
      },
    },
  );
  if (!res.ok) {
    return new Response('Artifact not found', {
      status: res.status,
      headers: {
        'cache-control': 'private, no-store, max-age=0',
      },
    });
  }

  const contentType =
    res.headers.get('content-type') || 'application/octet-stream';
  const body = await res.arrayBuffer();

  return new Response(body, {
    headers: {
      'content-type': contentType,
      'cache-control': 'private, no-store, max-age=0',
      pragma: 'no-cache',
      'x-content-type-options': 'nosniff',
    },
  });
}
