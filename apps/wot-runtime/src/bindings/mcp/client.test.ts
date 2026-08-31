import assert from 'node:assert/strict';
import { Readable } from 'node:stream';
import test from 'node:test';

import wotCore from '@node-wot/core';
import type { Content, SecurityScheme } from '@node-wot/core';

import { McpClient, listAllMcpResources, listAllMcpTools, readArguments } from './client.js';

const { Content: ContentClass } = wotCore as any;

/**
 * Wraps a string as node-wot Content, the shape node-wot hands to invokeResource.
 */
function jsonContent(text: string): Content {
  return new ContentClass('application/json', Readable.from([Buffer.from(text, 'utf-8')]));
}

/**
 * Returns the headers a client would send, which are private to the client.
 */
function headersOf(client: McpClient): Record<string, string> {
  return (client as any).headers;
}

test('readArguments returns an empty object when there is no input', async () => {
  assert.deepEqual(await readArguments(undefined), {});
  assert.deepEqual(await readArguments(jsonContent('')), {});
});

test('readArguments passes a JSON object through unchanged', async () => {
  assert.deepEqual(await readArguments(jsonContent('{"query":"pumps","limit":5}')), { query: 'pumps', limit: 5 });
});

test('readArguments treats explicit null as no arguments', async () => {
  assert.deepEqual(await readArguments(jsonContent('null')), {});
});

test('readArguments rejects a non-object payload with a usable message', async () => {
  await assert.rejects(
    () => readArguments(jsonContent('[1,2,3]')),
    (error: Error) => error.message.includes('an array'),
  );
  await assert.rejects(
    () => readArguments(jsonContent('"just a string"')),
    (error: Error) => error.message.includes('string'),
  );
});

test('readArguments rejects malformed JSON', async () => {
  await assert.rejects(() => readArguments(jsonContent('{not json')));
});

test('setSecurity sends no headers for nosec', () => {
  const client = new McpClient();

  assert.equal(client.setSecurity([{ scheme: 'nosec' }] as SecurityScheme[]), true);
  assert.deepEqual(headersOf(client), {});
});

test('setSecurity builds a bearer Authorization header', () => {
  const client = new McpClient();

  assert.equal(client.setSecurity([{ scheme: 'bearer' }] as SecurityScheme[], { token: 'abc123' }), true);
  assert.deepEqual(headersOf(client), { Authorization: 'Bearer abc123' });
});

test('setSecurity builds a basic Authorization header', () => {
  const client = new McpClient();

  assert.equal(
    client.setSecurity([{ scheme: 'basic' }] as SecurityScheme[], { username: 'ada', password: 'lovelace' }),
    true,
  );
  assert.deepEqual(headersOf(client), { Authorization: `Basic ${Buffer.from('ada:lovelace').toString('base64')}` });
});

test('setSecurity uses the security definition name for an apikey header', () => {
  const client = new McpClient();

  assert.equal(
    client.setSecurity([{ scheme: 'apikey', name: 'X-Tenant-Key' }] as SecurityScheme[], { apikey: 'k-1' }),
    true,
  );
  assert.deepEqual(headersOf(client), { 'X-Tenant-Key': 'k-1' });
});

test('setSecurity falls back to a conventional apikey header name', () => {
  const client = new McpClient();

  client.setSecurity([{ scheme: 'apikey' }] as SecurityScheme[], { apikey: 'k-2' });

  assert.deepEqual(headersOf(client), { 'X-API-Key': 'k-2' });
});

test('setSecurity reports failure when credentials are missing or the wrong shape', () => {
  const client = new McpClient();

  assert.equal(client.setSecurity([{ scheme: 'bearer' }] as SecurityScheme[]), false);
  assert.equal(client.setSecurity([{ scheme: 'bearer' }] as SecurityScheme[], { apikey: 'wrong-field' }), false);
});

test('setSecurity reports failure for a scheme the binding cannot apply', () => {
  const client = new McpClient();

  assert.equal(client.setSecurity([{ scheme: 'oauth2' }] as SecurityScheme[], { token: 'x' }), false);
});

test('writing a resource is refused, since MCP has no such operation', async () => {
  const client = new McpClient();

  await assert.rejects(
    () => client.writeResource({ href: 'mcp+https://host/mcp' } as any),
    (error: Error) => error.message.includes('does not support writing'),
  );
});

test('description pagination collects every tool and resource page', async () => {
  const toolCursors: Array<string | undefined> = [];
  const resourceCursors: Array<string | undefined> = [];
  const client = {
    async listTools(params?: { cursor?: string }) {
      toolCursors.push(params?.cursor);
      return params?.cursor
        ? { tools: [{ name: 'second', inputSchema: {} }] }
        : { tools: [{ name: 'first', inputSchema: {} }], nextCursor: 'tools-2' };
    },
    async listResources(params?: { cursor?: string }) {
      resourceCursors.push(params?.cursor);
      return params?.cursor
        ? { resources: [{ uri: 'file:///second' }] }
        : { resources: [{ uri: 'file:///first' }], nextCursor: 'resources-2' };
    },
  };

  const tools = await listAllMcpTools(client as any);
  const resources = await listAllMcpResources(client as any);

  assert.deepEqual(
    tools.map((tool) => tool.name),
    ['first', 'second'],
  );
  assert.deepEqual(
    resources.map((resource) => resource.uri),
    ['file:///first', 'file:///second'],
  );
  assert.deepEqual(toolCursors, [undefined, 'tools-2']);
  assert.deepEqual(resourceCursors, [undefined, 'resources-2']);
});
