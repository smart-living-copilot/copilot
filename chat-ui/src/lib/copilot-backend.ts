const copilotUrl = process.env.COPILOT_URL || 'http://copilot:8123';
const internalApiKey = process.env.INTERNAL_API_KEY || '';

function buildHeaders(headers?: HeadersInit) {
  const merged = new Headers(headers);
  if (internalApiKey) {
    merged.set('Authorization', `Bearer ${internalApiKey}`);
  }
  return merged;
}

export async function fetchCopilot(path: string, init: RequestInit = {}) {
  return fetch(`${copilotUrl}${path}`, {
    ...init,
    cache: init.cache ?? 'no-store',
    headers: buildHeaders(init.headers),
  });
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
