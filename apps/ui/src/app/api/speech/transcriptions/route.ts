import { jobRunnerFetch } from '@/lib/job-runner-api';

export async function POST(req: Request) {
  const body = await req.arrayBuffer();
  const res = await jobRunnerFetch('/speech/transcriptions', {
    method: 'POST',
    headers: {
      'Content-Type': req.headers.get('content-type') || 'audio/webm',
      'X-Filename': req.headers.get('x-filename') || 'answer.webm',
    },
    body,
  });
  const text = await res.text();

  return new Response(text, {
    status: res.status,
    headers: {
      'Content-Type': res.headers.get('content-type') || 'application/json',
    },
  });
}
