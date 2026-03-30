export async function wotFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const base = process.env.WOT_API_URL || 'http://localhost:8000/api';
  const token = process.env.WOT_REGISTRY_TOKEN || '';
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers instanceof Headers
        ? Object.fromEntries(init.headers.entries())
        : (init.headers ?? {})),
    },
  });
  return res;
}

export async function wotJson<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await wotFetch(path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      (body as { detail?: string }).detail || `Request failed (${res.status})`,
    );
  }
  return res.json();
}
