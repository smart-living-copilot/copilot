import assert from 'node:assert/strict';
import test from 'node:test';

import { encodeInteractionOutputPayload } from './payloads.js';

test('schema-less interaction output falls back to its raw response bytes', async () => {
  const body = Buffer.from('<gml:FeatureCollection/>');
  let arrayBufferReads = 0;
  let valueReads = 0;
  const result = await encodeInteractionOutputPayload({
    form: {
      href: 'wotbot+provider://runtime/things/example/actions/download_gml',
      response: { contentType: 'application/gml+xml' },
    },
    schema: undefined,
    value: async () => {
      valueReads += 1;
      return undefined;
    },
    arrayBuffer: async () => {
      arrayBufferReads += 1;
      return body;
    },
  });

  assert.equal(arrayBufferReads, 1);
  assert.equal(valueReads, 0);
  assert.deepEqual(result.body, body);
  assert.equal(result.contentType, 'application/gml+xml');
  assert.equal(result.sourceProtocol, 'wotbot+provider');
});

test('schema-less action with an empty response remains empty', async () => {
  let arrayBufferReads = 0;
  const result = await encodeInteractionOutputPayload({
    form: {
      href: 'https://device.example/actions/restart',
      response: { contentType: 'application/octet-stream' },
    },
    schema: undefined,
    value: async () => undefined,
    arrayBuffer: async () => {
      arrayBufferReads += 1;
      return new ArrayBuffer(0);
    },
  });

  assert.equal(arrayBufferReads, 1);
  assert.equal(result.body.length, 0);
  assert.equal(result.contentType, 'application/octet-stream');
  assert.equal(result.sourceProtocol, 'https');
});
