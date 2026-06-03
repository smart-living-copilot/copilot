import { NextRequest, NextResponse } from 'next/server';

import { jobRunnerFetch } from '@/lib/job-runner-api';

export async function GET(req: NextRequest) {
  const query = req.nextUrl.searchParams.toString();
  const res = await jobRunnerFetch(`/jobs${query ? `?${query}` : ''}`);
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function POST(req: NextRequest) {
  const body = await req.text();
  const res = await jobRunnerFetch('/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
