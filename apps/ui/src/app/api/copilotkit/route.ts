import { HttpAgent } from '@ag-ui/client';
import {
  CopilotRuntime,
  createCopilotEndpointSingleRoute,
} from '@copilotkit/runtime/v2';

import { filterWotbotEventStream } from '@/lib/wotbot-stream';
import { getWotbotUrl } from '@/lib/backend-env';

const wotbotUrl = getWotbotUrl();

const runtime = new CopilotRuntime({
  agents: {
    wotbot: new HttpAgent({ url: `${wotbotUrl}/ag-ui` }),
  },
});

// @copilotkit/runtime/v2 (a thin re-export of @copilotkitnext/runtime --
// import from the /v2 subpath, not the standalone @copilotkitnext/runtime
// package directly, which npm flags deprecated in favor of this), not the
// bare @copilotkit/runtime import this route used before: the client
// (@copilotkit/react-core/v2) speaks v2's single-endpoint JSON-RPC protocol
// -- including "agent/stop", which stops the run by calling the agent's own
// abortRun() (HttpAgent.abortRun() aborts the underlying fetch to wotbot's
// /ag-ui, so the cancellation actually reaches the backend). The bare v1
// import has no handler for that method at all -- clicking Stop silently
// did nothing server-side.
const app = createCopilotEndpointSingleRoute({
  runtime,
  basePath: '/api/copilotkit',
});

async function handleFilteredRequest(request: Request): Promise<Response> {
  const response = await app.fetch(request);
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
