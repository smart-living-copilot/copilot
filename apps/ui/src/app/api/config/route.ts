import { getReasoningEffortRuntimeConfig } from '@/lib/reasoning-effort-runtime-config';
import { fetchWotbot } from '@/lib/wotbot-backend';

/**
 * Serves the System info panel with both halves of the picture.
 *
 * The backend report says what the agent resolved; `ui` says what *this*
 * container resolved from its own environment for the settings it parses
 * independently. Composing them here is what makes the drift check possible at
 * all -- the settings page is a client component and cannot read `process.env`.
 */
export async function GET() {
  const response = await fetchWotbot('/api/config');
  const body = await response.text();

  if (!response.ok) {
    return new Response(body, {
      status: response.status,
      headers: {
        'Content-Type':
          response.headers.get('content-type') || 'application/json',
      },
    });
  }

  return Response.json({
    backend: JSON.parse(body),
    ui: {
      reasoningEffort: getReasoningEffortRuntimeConfig(),
    },
  });
}
