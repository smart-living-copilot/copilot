import { NextRequest, NextResponse } from 'next/server';

import { jobRunnerFetch } from '@/lib/job-runner-api';

type RouteContext = { params: Promise<{ jobId: string }> };

export async function POST(req: NextRequest, context: RouteContext) {
  const { jobId } = await context.params;
  const body = await req.text();
  const res = await jobRunnerFetch(`/jobs/${encodeURIComponent(jobId)}/reply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
