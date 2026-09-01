import assert from 'node:assert/strict';
import test from 'node:test';

import { ProviderClient } from './client.js';

test('provider client preserves the TD response type when the upstream type is generic', async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; init: RequestInit | undefined }> = [];
  const handle = 'a'.repeat(43);
  globalThis.fetch = async (input, init) => {
    requests.push({ url: String(input), init });
    if (requests.length === 1) {
      return new Response(
        JSON.stringify({
          kind: 'download',
          title: 'Air data',
          download_url: `/api/discovery/downloads/${handle}`,
          expires_in_seconds: 300,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    return new Response(Buffer.from([0x50, 0x4b, 0x03, 0x04]), {
      status: 200,
      headers: { 'Content-Type': 'application/octet-stream' },
    });
  };
  try {
    const thingId = 'urn:wotbot:external:edc-v3:abc';
    const encoded = Buffer.from(thingId).toString('base64url');
    const content = await new ProviderClient().invokeResource({
      href: `wotbot+provider://runtime/things/${encoded}/actions/download_asset`,
      response: { contentType: 'application/zip' },
    } as any);
    assert.equal(requests[0].url, 'http://localhost:8000/api/discovery/runtime/invoke');
    assert.deepEqual(JSON.parse(String(requests[0].init?.body)), {
      thing_id: thingId,
      action: 'download_asset',
      input: null,
      uri_variables: {},
    });
    assert.equal(requests[1].url, `http://localhost:8000/api/discovery/runtime/downloads/${handle}`);
    for (const request of requests) {
      const headers = request.init?.headers as Record<string, string>;
      assert.equal(headers['X-Registry-Service'], 'wot_runtime');
      assert.equal(headers['X-Registry-Service-Token'], 'test-token');
    }
    assert.equal(content.type, 'application/zip');
    assert.deepEqual(await content.toBuffer(), Buffer.from([0x50, 0x4b, 0x03, 0x04]));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('provider client rejects dispatcher output that is not an internal capability', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ download_url: 'https://attacker.example/data' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  try {
    const thingId = Buffer.from('urn:test').toString('base64url');
    await assert.rejects(
      new ProviderClient().invokeResource({
        href: `wotbot+provider://runtime/things/${thingId}/actions/download_csv`,
      } as any),
      /invalid result kind/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('provider client returns negotiated API responses and forwards URI variables', async () => {
  const originalFetch = globalThis.fetch;
  let request: RequestInit | undefined;
  globalThis.fetch = async (_input, init) => {
    request = init;
    return Response.json({
      kind: 'response',
      content_type: 'application/json',
      body_base64: Buffer.from(JSON.stringify({ name: 'Ada' })).toString('base64'),
    });
  };
  try {
    const thingId = 'urn:wotbot:external:edc-v3:api';
    const encoded = Buffer.from(thingId).toString('base64url');
    const content = await new ProviderClient().invokeResource(
      {
        href: `wotbot+provider://runtime/things/${encoded}/actions/getBrewery?id=42`,
      } as any,
      undefined,
    );
    assert.deepEqual(JSON.parse(String(request?.body)), {
      thing_id: thingId,
      action: 'getBrewery',
      input: null,
      uri_variables: { id: '42' },
    });
    assert.equal(content.type, 'application/json');
    assert.deepEqual(JSON.parse((await content.toBuffer()).toString('utf8')), {
      name: 'Ada',
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('provider client returns only the sanitized credential challenge from HTTP 428', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        detail: {
          status: 'credential_required',
          owner_kind: 'source',
          source_id: 'urn:source',
          security_name: 'source_sc',
          scheme: 'apikey',
          token: 'must-not-escape',
        },
      }),
      { status: 428, headers: { 'Content-Type': 'application/json' } },
    );
  try {
    const encoded = Buffer.from('urn:source').toString('base64url');
    const content = await new ProviderClient().invokeResource({
      href: `wotbot+provider://runtime/things/${encoded}/actions/discover`,
    } as any);
    assert.deepEqual(JSON.parse((await content.toBuffer()).toString('utf8')), {
      status: 'credential_required',
      owner_kind: 'source',
      source_id: 'urn:source',
      security_name: 'source_sc',
      scheme: 'apikey',
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('provider client accepts supported TD security without forwarding it', () => {
  const client = new ProviderClient();
  for (const scheme of ['nosec', 'apikey', 'bearer', 'basic', 'oauth2']) {
    assert.equal(client.setSecurity([{ scheme }] as any), true);
  }
  assert.equal(client.setSecurity([{ scheme: 'digest' }] as any), false);
});
