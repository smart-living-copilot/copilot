import { NextRequest, NextResponse } from 'next/server';

import { jobRunnerFetch } from '@/lib/job-runner-api';

type RouteContext = { params: Promise<{ jobId: string }> };

export async function GET(_req: NextRequest, context: RouteContext) {
  const { jobId } = await context.params;
  const res = await jobRunnerFetch(`/jobs/${encodeURIComponent(jobId)}/runs`);
  return NextResponse.json(await res.json(), { status: res.status });
}
