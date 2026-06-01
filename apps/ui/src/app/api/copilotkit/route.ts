import {
  CopilotRuntime,
  EmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from '@copilotkit/runtime';
import { LangGraphHttpAgent } from '@copilotkit/runtime/langgraph';

import { filterCopilotEventStream } from '@/lib/copilot-stream';
import { getCopilotUrl } from '@/lib/backend-env';

const copilotUrl = getCopilotUrl();

const runtime = new CopilotRuntime({
  agents: {
    copilot: new LangGraphHttpAgent({
      url: `${copilotUrl}/ag-ui`,
    }),
  },
});

const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
  runtime,
  serviceAdapter: new EmptyAdapter(),
  endpoint: '/api/copilotkit',
});

async function handleFilteredRequest(request: Request): Promise<Response> {
  const response = await handleRequest(request);
  const contentType = response.headers.get('content-type') ?? '';

  if (!contentType.includes('text/event-stream') || !response.body) {
    return response;
  }

  return new Response(filterCopilotEventStream(response.body), {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

export const POST = handleFilteredRequest;
export const GET = handleFilteredRequest;
