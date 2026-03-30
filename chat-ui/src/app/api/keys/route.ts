import { NextRequest, NextResponse } from 'next/server';
import { wotFetch } from '@/lib/wot-api';

export async function GET() {
  const res = await wotFetch('/keys');
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function POST(req: NextRequest) {
  const body = await req.text();
  const res = await wotFetch('/keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
