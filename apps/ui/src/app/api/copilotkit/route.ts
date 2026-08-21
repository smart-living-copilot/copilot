import { HttpAgent } from '@ag-ui/client';
import {
  CopilotRuntime,
  createCopilotEndpointSingleRoute,
} from '@copilotkit/runtime/v2';

import { getWotbotUrl } from '@/lib/backend-env';
import { WotbotAgentRunner } from '@/lib/wotbot-agent-runner';
import { WotbotEventMiddleware } from '@/lib/wotbot-middleware';

const wotbotUrl = getWotbotUrl();
const wotbotAgent = new HttpAgent({ url: `${wotbotUrl}/ag-ui` }).use(
  new WotbotEventMiddleware(),
);

const runtime = new CopilotRuntime({
  agents: {
    wotbot: wotbotAgent,
  },
  runner: new WotbotAgentRunner(),
});

// Keep this on the v2 single-route API: its agent/stop handler reaches
// HttpAgent.abortRun(), allowing the middleware to normalize the abort event.
const app = createCopilotEndpointSingleRoute({
  runtime,
  basePath: '/api/copilotkit',
});

export const POST = app.fetch;
export const GET = app.fetch;
