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
    throw new Error(
      (body as { detail?: string }).detail || `Request failed (${res.status})`,
    );
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
