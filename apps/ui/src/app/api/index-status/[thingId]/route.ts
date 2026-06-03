import { NextRequest, NextResponse } from 'next/server';
import { wotFetch } from '@/lib/wot-api';

type RouteContext = { params: Promise<{ thingId: string }> };

export async function GET(_req: NextRequest, context: RouteContext) {
  const { thingId } = await context.params;
  const res = await wotFetch(`/index-status/${encodeURIComponent(thingId)}`);
  return NextResponse.json(await res.json(), { status: res.status });
}
