import { NextResponse, type NextRequest } from 'next/server';

import { isPanelHostname, toPanelLabel } from '@/lib/panel-origin';

/**
 * Keeps the app off the panel origins.
 *
 * Panels are served by this same app under a different host, which means a
 * panel's own origin also answers `/api/things`, `/api/keys` and every other
 * route -- and from inside the panel those are *same-origin* requests. The
 * panel CSP has no `'self'` in `connect-src`, so the browser already blocks
 * that, but relying on one control for something this sharp is a bad trade.
 *
 * On a panel host only the two document routes exist. Everything else 404s, so
 * a CSP mistake alone cannot expose the API. Device access stays where it
 * belongs: the capability-checked `window.wot` bridge, which is postMessage and
 * therefore governed by neither CSP nor this.
 */
const PANEL_DOCUMENT_ROUTES = [
  /^\/api\/panels\/([^/]+)\/render$/,
  /^\/api\/artifacts\/(.+)$/,
];

export function proxy(request: NextRequest) {
  // The Host header, not `nextUrl.hostname`: the latter comes from the server's
  // own base URL and stays "localhost" no matter which host was asked for,
  // which would quietly disable this whole guard.
  const host = request.headers.get('host') ?? request.nextUrl.hostname;
  const hostname = host.split(':')[0].toLowerCase();

  if (!isPanelHostname(hostname)) {
    return NextResponse.next();
  }

  // The host must match the document it is asking for. Without this every panel
  // host serves every artifact, so one panel could load another's output as a
  // same-origin image and read the pixels back off a canvas.
  const label = hostname.split('.')[0];
  const isOwnDocument = PANEL_DOCUMENT_ROUTES.some((route) => {
    const match = route.exec(request.nextUrl.pathname);
    return match ? toPanelLabel(decodeURIComponent(match[1])) === label : false;
  });

  return isOwnDocument
    ? NextResponse.next()
    : new NextResponse('Not found', { status: 404 });
}

export const config = {
  // Static assets are served from the app origin, so the panel host never needs
  // them; excluding them keeps this off the hot path for normal traffic.
  matcher: '/((?!_next/static|_next/image|favicon.ico).*)',
};
