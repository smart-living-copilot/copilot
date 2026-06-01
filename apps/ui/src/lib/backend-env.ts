const defaultCopilotUrl = 'http://copilot:8123';
const defaultCodeExecutorUrl = 'http://code-executor:8888';

function cleanBaseUrl(value: string): string {
  return value.replace(/\/+$/, '');
}

export function getCopilotUrl(): string {
  return cleanBaseUrl(
    process.env.COPILOT_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      defaultCopilotUrl,
  );
}

export function getJobRunnerUrl(): string {
  return cleanBaseUrl(process.env.JOB_RUNNER_URL || getCopilotUrl());
}

export function getWotApiUrl(): string {
  return cleanBaseUrl(process.env.WOT_API_URL || `${getCopilotUrl()}/api`);
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
