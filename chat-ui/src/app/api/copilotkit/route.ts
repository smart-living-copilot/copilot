import {
  CopilotRuntime,
  EmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from '@copilotkit/runtime';
import { LangGraphHttpAgent } from '@copilotkit/runtime/langgraph';

const copilotUrl = process.env.COPILOT_URL || 'http://copilot:8123';

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

export const POST = handleRequest;
export const GET = handleRequest;
