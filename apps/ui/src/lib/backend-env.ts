const defaultWotbotUrl = 'http://wotbot:8123';
const defaultCodeExecutorUrl = 'http://code-executor:8888';

function cleanBaseUrl(value: string): string {
  return value.replace(/\/+$/, '');
}

export function getWotbotUrl(): string {
  return cleanBaseUrl(
    process.env.WOTBOT_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      defaultWotbotUrl,
  );
}

export function getJobRunnerUrl(): string {
  return cleanBaseUrl(process.env.JOB_RUNNER_URL || getWotbotUrl());
}

export function getWotApiUrl(): string {
  return cleanBaseUrl(process.env.WOT_API_URL || `${getWotbotUrl()}/api`);
}

export function getCodeExecutorUrl(): string {
  return cleanBaseUrl(process.env.CODE_EXECUTOR_URL || defaultCodeExecutorUrl);
}

export function backendUnavailableResponse(
  service: string,
  baseUrl: string,
  error: unknown,
): Response {
  const detail =
    error instanceof Error
      ? `${service} is unavailable at ${baseUrl}: ${error.message}`
      : `${service} is unavailable at ${baseUrl}`;

  return Response.json({ detail }, { status: 502 });
}
