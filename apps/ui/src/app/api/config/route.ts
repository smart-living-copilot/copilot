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

  let backend: unknown;
  try {
    backend = JSON.parse(body);
  } catch {
    // A 200 that is not JSON means something answered for the backend -- a
    // proxy error page, a truncated body. Report it as the panel's own error
    // rather than throwing and returning an opaque 500.
    return Response.json(
      { detail: 'The backend returned a malformed configuration response.' },
      { status: 502 },
    );
  }

  return Response.json({
    backend,
    ui: {
      reasoningEffort: getReasoningEffortRuntimeConfig(),
    },
  });
}
