import { NextRequest, NextResponse } from 'next/server';
import { wotFetch } from '@/lib/wot-api';

type RouteContext = { params: Promise<{ keyId: string }> };

export async function DELETE(_req: NextRequest, context: RouteContext) {
  const { keyId } = await context.params;
  const res = await wotFetch(`/keys/${encodeURIComponent(keyId)}`, {
    method: 'DELETE',
  });
  if (res.status === 204) return new NextResponse(null, { status: 204 });
  return NextResponse.json(await res.json(), { status: res.status });
}
