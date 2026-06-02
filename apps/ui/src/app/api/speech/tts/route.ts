import { jobRunnerFetch } from '@/lib/job-runner-api';

export async function POST(req: Request) {
  const body = await req.text();
  const res = await jobRunnerFetch('/speech/tts', {
    method: 'POST',
    headers: {
      Accept: 'audio/mpeg',
      'Content-Type': 'application/json',
    },
    body,
  });
  const headers = new Headers({
    'Content-Type': res.headers.get('content-type') || 'audio/mpeg',
    'Cache-Control':
      res.headers.get('cache-control') || 'private, no-store, max-age=0',
  });
  const speechCache = res.headers.get('x-speech-cache');
  if (speechCache) {
    headers.set('X-Speech-Cache', speechCache);
  }

  return new Response(res.body, {
    status: res.status,
    headers,
  });
}
