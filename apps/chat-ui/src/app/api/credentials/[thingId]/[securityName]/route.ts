import { NextRequest, NextResponse } from 'next/server';
import { wotFetch } from '@/lib/wot-api';

type RouteContext = {
  params: Promise<{ thingId: string; securityName: string }>;
};

export async function PUT(req: NextRequest, context: RouteContext) {
  const { thingId, securityName } = await context.params;
  const body = await req.text();
  const res = await wotFetch(
    `/credentials/${encodeURIComponent(thingId)}/${encodeURIComponent(securityName)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body,
    },
  );
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function DELETE(_req: NextRequest, context: RouteContext) {
  const { thingId, securityName } = await context.params;
  const res = await wotFetch(
    `/credentials/${encodeURIComponent(thingId)}/${encodeURIComponent(securityName)}`,
    { method: 'DELETE' },
  );
  if (res.status === 204) return new NextResponse(null, { status: 204 });
  return NextResponse.json(await res.json(), { status: res.status });
}
