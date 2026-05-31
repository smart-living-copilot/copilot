import { NextResponse } from 'next/server';

import { jobRunnerFetch } from '@/lib/job-runner-api';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET() {
  const res = await jobRunnerFetch('/jobs/events', {
    headers: { Accept: 'text/event-stream' },
    cache: 'no-store',
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return NextResponse.json(body, { status: res.status });
  }

  if (!res.body) {
    return NextResponse.json(
      { detail: 'Upstream stream unavailable' },
      { status: 502 },
    );
  }

  return new Response(res.body, {
    status: res.status,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  });
}
