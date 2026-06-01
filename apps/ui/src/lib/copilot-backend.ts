import { backendUnavailableResponse, getCopilotUrl } from '@/lib/backend-env';

const internalApiKey = process.env.INTERNAL_API_KEY || '';

function buildHeaders(headers?: HeadersInit) {
  const merged = new Headers(headers);
  if (internalApiKey) {
    merged.set('Authorization', `Bearer ${internalApiKey}`);
  }
  return merged;
}

export async function fetchCopilot(path: string, init: RequestInit = {}) {
  const copilotUrl = getCopilotUrl();

  try {
    return await fetch(`${copilotUrl}${path}`, {
      ...init,
      cache: init.cache ?? 'no-store',
      headers: buildHeaders(init.headers),
    });
  } catch (error) {
    if (init.signal?.aborted) {
      throw error;
    }
    return backendUnavailableResponse('Copilot backend', copilotUrl, error);
  }
}

export async function proxyCopilotJson(path: string, init: RequestInit = {}) {
  const response = await fetchCopilot(path, init);
  const body = await response.text();
  return new Response(body, {
    status: response.status,
    headers: {
      'Content-Type':
        response.headers.get('content-type') || 'application/json',
    },
  });
}
