import { NextRequest, NextResponse } from 'next/server';

import { wotFetch } from '@/lib/wot-api';

type RouteContext = {
  params: Promise<{ thingId: string; actionName: string }>;
};

export async function POST(req: NextRequest, context: RouteContext) {
  const { thingId, actionName } = await context.params;
  const body = await req.text();
  const res = await wotFetch(
    `/virtual-things/${encodeURIComponent(thingId)}/actions/${encodeURIComponent(actionName)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    },
  );
  return NextResponse.json(await res.json(), { status: res.status });
}
