import { NextRequest, NextResponse } from 'next/server';

import { wotFetch } from '@/lib/wot-api';

type RouteContext = {
  params: Promise<{ thingId: string; eventName: string }>;
};

export async function POST(req: NextRequest, context: RouteContext) {
  const { thingId, eventName } = await context.params;
  const body = await req.text();
  const res = await wotFetch(
    `/virtual-things/${encodeURIComponent(thingId)}/events/${encodeURIComponent(eventName)}/evaluate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    },
  );
  return NextResponse.json(await res.json(), { status: res.status });
}
