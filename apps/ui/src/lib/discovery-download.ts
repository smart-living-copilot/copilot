const FORWARDED_HEADERS = [
  'content-type',
  'content-length',
  'content-range',
  'accept-ranges',
  'content-disposition',
  'content-encoding',
  'etag',
  'last-modified',
  'x-content-type-options',
] as const;

export function proxyDiscoveryDownload(response: Response): Response {
  const headers = new Headers();
  for (const name of FORWARDED_HEADERS) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set('cache-control', 'private, no-store, max-age=0');
  return new Response(response.body, { status: response.status, headers });
}
