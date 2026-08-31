import assert from 'node:assert/strict';
import test from 'node:test';

import type { Content } from '@node-wot/core';

import { resourceResultToContent, toolResultToContent } from './content.js';

/**
 * Reads a Content back into its content type and decoded body.
 */
async function readContent(content: Content): Promise<{ type: string; body: Buffer }> {
  return { type: content.type, body: await content.toBuffer() };
}

test('a single text block that is not JSON becomes text/plain', async () => {
  const { type, body } = await readContent(toolResultToContent('t', { content: [{ type: 'text', text: 'hello' }] }));

  assert.equal(type, 'text/plain');
  assert.equal(body.toString('utf-8'), 'hello');
});

test('a single text block that parses as JSON becomes application/json', async () => {
  const { type, body } = await readContent(
    toolResultToContent('t', { content: [{ type: 'text', text: '{"count": 2}' }] }),
  );

  assert.equal(type, 'application/json');
  assert.deepEqual(JSON.parse(body.toString('utf-8')), { count: 2 });
});

test('an image block is decoded to its declared mime type', async () => {
  const data = Buffer.from('binary-ish').toString('base64');
  const { type, body } = await readContent(
    toolResultToContent('t', { content: [{ type: 'image', data, mimeType: 'image/png' }] }),
  );

  assert.equal(type, 'image/png');
  assert.equal(body.toString('utf-8'), 'binary-ish');
});

test('an embedded resource uses the resource mime type', async () => {
  const { type, body } = await readContent(
    toolResultToContent('t', {
      content: [{ type: 'resource', resource: { uri: 'file:///a.csv', text: 'a,b', mimeType: 'text/csv' } }],
    }),
  );

  assert.equal(type, 'text/csv');
  assert.equal(body.toString('utf-8'), 'a,b');
});

test('structuredContent is preferred over re-parsing text blocks', async () => {
  const { type, body } = await readContent(
    toolResultToContent('t', {
      content: [{ type: 'text', text: 'ignored' }],
      structuredContent: { ok: true },
    }),
  );

  assert.equal(type, 'application/json');
  assert.deepEqual(JSON.parse(body.toString('utf-8')), { ok: true });
});

test('multiple blocks are handed back intact rather than partially dropped', async () => {
  const blocks = [
    { type: 'text', text: 'one' },
    { type: 'text', text: 'two' },
  ];
  const { type, body } = await readContent(toolResultToContent('t', { content: blocks }));

  assert.equal(type, 'application/json');
  assert.deepEqual(JSON.parse(body.toString('utf-8')), blocks);
});

test('an empty result is null rather than an error', async () => {
  const { body } = await readContent(toolResultToContent('t', { content: [] }));

  assert.equal(body.toString('utf-8'), 'null');
});

test('isError raises rather than returning a successful payload', () => {
  assert.throws(
    () => toolResultToContent('search', { content: [{ type: 'text', text: 'rate limited' }], isError: true }),
    (error: Error) => error.message.includes('search') && error.message.includes('rate limited'),
  );
});

test('isError with no text block still reports a usable message', () => {
  assert.throws(
    () =>
      toolResultToContent('search', { content: [{ type: 'image', data: 'x', mimeType: 'image/png' }], isError: true }),
    (error: Error) => error.message.includes('search'),
  );
});

test('resourceResultToContent unwraps a bare resource body', async () => {
  const { type, body } = await readContent(
    resourceResultToContent('file:///a.json', {
      contents: [{ uri: 'file:///a.json', text: '{"a":1}', mimeType: 'application/json' }],
    }),
  );

  assert.equal(type, 'application/json');
  assert.deepEqual(JSON.parse(body.toString('utf-8')), { a: 1 });
});

test('resourceResultToContent fails when a resource returned nothing', () => {
  assert.throws(
    () => resourceResultToContent('file:///missing', { contents: [] }),
    (error: Error) => error.message.includes('file:///missing'),
  );
});
