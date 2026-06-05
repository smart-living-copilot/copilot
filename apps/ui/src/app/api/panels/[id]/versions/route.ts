import { NextResponse } from 'next/server';

import { wotFetch } from '@/lib/wot-api';

type RouteContext = { params: Promise<{ id: string }> };

export async function GET(_req: Request, context: RouteContext) {
  const { id } = await context.params;
  const res = await wotFetch(`/panels/${encodeURIComponent(id)}/versions`);
  return NextResponse.json(await res.json(), { status: res.status });
}
