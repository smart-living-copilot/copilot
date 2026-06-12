import { NextRequest, NextResponse } from 'next/server';

import { wotFetch } from '@/lib/wot-api';

export async function GET(req: NextRequest) {
  const query = req.nextUrl.searchParams.toString();
  const res = await wotFetch(
    `/virtual-things/definitions${query ? `?${query}` : ''}`,
  );
  return NextResponse.json(await res.json(), { status: res.status });
}
