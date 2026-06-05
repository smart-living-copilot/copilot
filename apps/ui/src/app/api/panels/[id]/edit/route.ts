import { NextRequest, NextResponse } from 'next/server';

import { wotFetch } from '@/lib/wot-api';

type RouteContext = { params: Promise<{ id: string }> };

export async function POST(req: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  const body = await req.text();
  const res = await wotFetch(`/panels/${encodeURIComponent(id)}/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
