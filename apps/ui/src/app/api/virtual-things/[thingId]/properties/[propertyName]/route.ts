import { NextRequest, NextResponse } from 'next/server';

import { wotFetch } from '@/lib/wot-api';

type RouteContext = {
  params: Promise<{ thingId: string; propertyName: string }>;
};

export async function GET(_req: NextRequest, context: RouteContext) {
  const { thingId, propertyName } = await context.params;
  const res = await wotFetch(
    `/virtual-things/${encodeURIComponent(thingId)}/properties/${encodeURIComponent(propertyName)}`,
  );
  return NextResponse.json(await res.json(), { status: res.status });
}
