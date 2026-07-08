import {
  CopilotRuntime,
  EmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from '@copilotkit/runtime';
import { LangGraphHttpAgent } from '@copilotkit/runtime/langgraph';

import { filterWotbotEventStream } from '@/lib/wotbot-stream';
import { getWotbotUrl } from '@/lib/backend-env';

const wotbotUrl = getWotbotUrl();

const runtime = new CopilotRuntime({
  agents: {
    wotbot: new LangGraphHttpAgent({
      url: `${wotbotUrl}/ag-ui`,
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

  return new Response(filterWotbotEventStream(response.body), {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

export const POST = handleFilteredRequest;
export const GET = handleFilteredRequest;
