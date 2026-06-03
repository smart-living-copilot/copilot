import { NextResponse } from 'next/server';
import { wotFetch } from '@/lib/wot-api';

export async function GET() {
  const res = await wotFetch('/keys/scopes');
  return NextResponse.json(await res.json(), { status: res.status });
}
