export async function httpClient(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.headers instanceof Headers
        ? Object.fromEntries(options.headers.entries())
        : (options.headers ?? {})),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === 'string') {
      throw new Error(detail);
    }
    if (
      detail &&
      typeof detail === 'object' &&
      'message' in detail &&
      typeof detail.message === 'string'
    ) {
      const errors =
        'errors' in detail && Array.isArray(detail.errors)
          ? ` ${detail.errors.join(' ')}`
          : '';
      throw new Error(`${detail.message}${errors}`);
    }
    throw new Error(`Request failed (${res.status})`);
  }
  return res;
}

export async function httpJson<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await httpClient(path, options);
  return res.json();
}
