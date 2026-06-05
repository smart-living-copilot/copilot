import { NextRequest, NextResponse } from 'next/server';

import { wotFetch } from '@/lib/wot-api';

// The generated mini-interfaces run in an opaque-origin sandbox and must talk to
// the runtime only through the trusted parent (postMessage bridge). Reject any
// request that did not originate same-origin so a misbehaving iframe cannot call
// these routes directly with a "null"/cross-site origin.
function isCrossOrigin(req: NextRequest): boolean {
  const origin = req.headers.get('origin');
  if (origin === 'null') {
    return true;
  }
  const site = req.headers.get('sec-fetch-site');
  if (
    site &&
    site !== 'same-origin' &&
    site !== 'same-site' &&
    site !== 'none'
  ) {
    return true;
  }
  return false;
}

function runtimePath(path: string[]): string {
  return `/wot/runtime/${path.map(encodeURIComponent).join('/')}`;
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  if (isCrossOrigin(req)) {
    return NextResponse.json(
      { detail: 'Cross-origin request rejected' },
      { status: 403 },
    );
  }
  const { path } = await params;
  const body = await req.text();
  const res = await wotFetch(runtimePath(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  if (isCrossOrigin(req)) {
    return NextResponse.json(
      { detail: 'Cross-origin request rejected' },
      { status: 403 },
    );
  }
  const { path } = await params;
  const query = req.nextUrl.searchParams.toString();
  const res = await wotFetch(`${runtimePath(path)}${query ? `?${query}` : ''}`);

  // Stream Server-Sent Events straight through for the /events endpoint.
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('text/event-stream')) {
    return new Response(res.body, {
      status: res.status,
      headers: {
        'content-type': 'text/event-stream',
        'cache-control': 'no-cache, no-transform',
        connection: 'keep-alive',
        'x-accel-buffering': 'no',
      },
    });
  }

  return NextResponse.json(await res.json(), { status: res.status });
}
