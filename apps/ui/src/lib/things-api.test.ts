import assert from 'node:assert/strict';
import test from 'node:test';

import { enrichThing } from './things-api';

test('enrichThing posts a draft document to the enrichment route', async () => {
  const calls: Array<{ input: string; init?: RequestInit }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    calls.push({ input: String(input), init });
    return new Response(
      JSON.stringify({
        enriched: { id: 'urn:thing:alpha', '@type': 'saref:TemperatureSensor' },
        diff: [
          {
            kind: 'type',
            path: '@type',
            value: 'saref:TemperatureSensor',
            label: 'Thing type',
          },
        ],
        validation: { ok: true, attempts: 1 },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
  }) as typeof fetch;

  try {
    const result = await enrichThing('urn:thing:alpha', {
      id: 'urn:thing:alpha',
    });

    assert.equal(calls[0]?.input, '/api/things/urn%3Athing%3Aalpha/enrich');
    assert.equal(calls[0]?.init?.method, 'POST');
    assert.equal(
      calls[0]?.init?.body,
      JSON.stringify({ document: { id: 'urn:thing:alpha' } }),
    );
    assert.equal(result.enriched['@type'], 'saref:TemperatureSensor');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
