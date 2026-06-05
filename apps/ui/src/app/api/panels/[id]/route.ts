import { NextRequest, NextResponse } from 'next/server';

import { wotFetch } from '@/lib/wot-api';

type RouteContext = { params: Promise<{ id: string }> };

export async function GET(req: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  const query = req.nextUrl.searchParams.toString();
  const res = await wotFetch(
    `/panels/${encodeURIComponent(id)}${query ? `?${query}` : ''}`,
  );
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function PATCH(req: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  const body = await req.text();
  const res = await wotFetch(`/panels/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function DELETE(_req: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  const res = await wotFetch(`/panels/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
