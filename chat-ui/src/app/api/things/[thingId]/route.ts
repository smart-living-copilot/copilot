import { NextRequest, NextResponse } from 'next/server';
import { wotFetch } from '@/lib/wot-api';

type RouteContext = { params: Promise<{ thingId: string }> };

export async function GET(_req: NextRequest, context: RouteContext) {
  const { thingId } = await context.params;
  const res = await wotFetch(`/things/${encodeURIComponent(thingId)}`);
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function PUT(req: NextRequest, context: RouteContext) {
  const { thingId } = await context.params;
  const body = await req.text();
  const res = await wotFetch(`/things/${encodeURIComponent(thingId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function DELETE(_req: NextRequest, context: RouteContext) {
  const { thingId } = await context.params;
  const res = await wotFetch(`/things/${encodeURIComponent(thingId)}`, {
    method: 'DELETE',
  });
  if (res.status === 204) return new NextResponse(null, { status: 204 });
  return NextResponse.json(await res.json(), { status: res.status });
}
