export async function jobRunnerFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const base = process.env.JOB_RUNNER_URL || 'http://job-runner:8890';
  const internalApiKey = process.env.INTERNAL_API_KEY || '';

  return fetch(`${base}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(internalApiKey
        ? { Authorization: `Bearer ${internalApiKey}` }
        : {}),
      ...(init.headers instanceof Headers
        ? Object.fromEntries(init.headers.entries())
        : (init.headers ?? {})),
    },
  });
}