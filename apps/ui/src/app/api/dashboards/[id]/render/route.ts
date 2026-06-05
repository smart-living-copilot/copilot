import { NextRequest } from 'next/server';

import { wotFetch } from '@/lib/wot-api';
import { PANEL_CSP } from '@/lib/panel-csp';

type RouteContext = { params: Promise<{ id: string }> };

// Serves the wrapped HTML document for a pinned panel into the sandboxed iframe.
// Same CSP as ephemeral panels: CDN loads allowed, all data egress blocked.
export async function GET(_req: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  const res = await wotFetch(`/panels/${encodeURIComponent(id)}/render`);

  if (!res.ok) {
    return new Response('Panel not found', { status: res.status });
  }

  const body = await res.text();
  return new Response(body, {
    headers: {
      'content-type': 'text/html; charset=utf-8',
      'cache-control': 'private, no-store, max-age=0',
      'x-content-type-options': 'nosniff',
      'content-security-policy': PANEL_CSP,
    },
  });
}
