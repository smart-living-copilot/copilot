import { NextRequest, NextResponse } from 'next/server';

import { wotFetch } from '@/lib/wot-api';

type RouteContext = { params: Promise<{ thingId: string }> };

export async function GET(req: NextRequest, context: RouteContext) {
  const { thingId } = await context.params;
  const query = req.nextUrl.searchParams.toString();
  const res = await wotFetch(
    `/virtual-things/definitions/${encodeURIComponent(thingId)}${query ? `?${query}` : ''}`,
  );
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function PUT(req: NextRequest, context: RouteContext) {
  const { thingId } = await context.params;
  const body = await req.text();
  const res = await wotFetch(
    `/virtual-things/definitions/${encodeURIComponent(thingId)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body,
    },
  );
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function DELETE(_req: NextRequest, context: RouteContext) {
  const { thingId } = await context.params;
  const res = await wotFetch(
    `/virtual-things/definitions/${encodeURIComponent(thingId)}`,
    {
      method: 'DELETE',
    },
  );
  return NextResponse.json(await res.json(), { status: res.status });
}
