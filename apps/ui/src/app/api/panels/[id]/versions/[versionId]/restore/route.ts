import { NextResponse } from 'next/server';

import { wotFetch } from '@/lib/wot-api';

type RouteContext = { params: Promise<{ id: string; versionId: string }> };

export async function POST(_req: Request, context: RouteContext) {
  const { id, versionId } = await context.params;
  const res = await wotFetch(
    `/panels/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}/restore`,
    { method: 'POST' },
  );
  return NextResponse.json(await res.json(), { status: res.status });
}
