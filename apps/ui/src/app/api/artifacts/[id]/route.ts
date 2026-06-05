import {
  backendUnavailableResponse,
  getCodeExecutorUrl,
} from '@/lib/backend-env';
import { PANEL_CSP } from '@/lib/panel-csp';

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const executorUrl = getCodeExecutorUrl();
  const internalApiKey = process.env.INTERNAL_API_KEY || '';

  let res: Response;
  try {
    res = await fetch(`${executorUrl}/artifacts/${encodeURIComponent(id)}`, {
      headers: {
        ...(internalApiKey
          ? { Authorization: `Bearer ${internalApiKey}` }
          : {}),
      },
    });
  } catch (error) {
    return backendUnavailableResponse('Code executor', executorUrl, error);
  }
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

  const headers: Record<string, string> = {
    'content-type': contentType,
    'cache-control': 'private, no-store, max-age=0',
    pragma: 'no-cache',
    'x-content-type-options': 'nosniff',
  };
  // Generated HTML panels run untrusted code under the shared panel CSP.
  if (contentType.includes('text/html')) {
    headers['content-security-policy'] = PANEL_CSP;
  }

  return new Response(body, { headers });
}
