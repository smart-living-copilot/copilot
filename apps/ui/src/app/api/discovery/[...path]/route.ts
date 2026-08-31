import { NextRequest, NextResponse } from 'next/server';

import { wotFetch } from '@/lib/wot-api';

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(req: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const suffix = path.map(encodeURIComponent).join('/');
  const query = req.nextUrl.search;
  const body = ['GET', 'HEAD'].includes(req.method)
    ? undefined
    : await req.text();
  const res = await wotFetch(`/discovery/${suffix}${query}`, {
    method: req.method,
    headers: body
      ? {
          'Content-Type': req.headers.get('content-type') || 'application/json',
        }
      : {},
    body: body || undefined,
  });
  if (res.status === 204) return new NextResponse(null, { status: 204 });
  return NextResponse.json(await res.json(), { status: res.status });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
