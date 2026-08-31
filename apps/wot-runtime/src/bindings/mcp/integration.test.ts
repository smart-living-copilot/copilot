import assert from 'node:assert/strict';
import { createServer, type Server } from 'node:http';
import { Readable } from 'node:stream';
import { after, before, test } from 'node:test';

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import wotCore from '@node-wot/core';
import type { Content, Form, SecurityScheme } from '@node-wot/core';
import { z } from 'zod';

import { McpClient } from './client.js';
import { activeSessionCount, closeAllSessions } from './session.js';

const { Content: ContentClass } = wotCore as any;

let httpServer: Server;
let transport: StreamableHTTPServerTransport;
let baseHref: string;

/**
 * Wraps a value as the JSON Content node-wot hands to invokeResource.
 */
function input(value: unknown): Content {
  return new ContentClass('application/json', Readable.from([Buffer.from(JSON.stringify(value), 'utf-8')]));
}

/**
 * Reads a Content back into its content type and text body.
 */
async function read(content: Content): Promise<{ type: string; text: string }> {
  return { type: content.type, text: (await content.toBuffer()).toString('utf-8') };
}

/**
 * Builds a form addressing the test server with the given extension fields.
 */
function form(fields: Record<string, unknown>): Form {
  return { href: baseHref, ...fields } as unknown as Form;
}

before(async () => {
  const mcp = new McpServer({ name: 'wot-runtime-tests', version: '1.0.0' });

  // inputSchema is a Zod shape, and the SDK strips arguments the shape does not
  // declare — so a tool that expects arguments must declare them here.
  mcp.registerTool(
    'greet',
    { description: 'Greets someone', inputSchema: { name: z.string().optional() } },
    async (args) => ({
      content: [{ type: 'text' as const, text: `hello ${String(args?.name ?? 'nobody')}` }],
    }),
  );

  mcp.registerTool('boom', { description: 'Always fails' }, async () => ({
    content: [{ type: 'text' as const, text: 'tool exploded' }],
    isError: true,
  }));

  mcp.registerResource('readme', 'file:///readme.txt', {}, async () => ({
    contents: [{ uri: 'file:///readme.txt', text: 'resource body', mimeType: 'text/plain' }],
  }));

  // A single transport serves one session, as a real server would per connected client.
  // The suite therefore connects once and shares that session: tearing it down mid-suite
  // would make the server reject the next handshake with "Server already initialized".
  transport = new StreamableHTTPServerTransport({ sessionIdGenerator: () => `test-${Date.now()}` });
  await mcp.connect(transport);

  httpServer = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => chunks.push(chunk));
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf-8');
      void transport.handleRequest(req, res, raw ? JSON.parse(raw) : undefined);
    });
  });

  // Port 0 takes whatever is free, so the suite never collides with a running service.
  await new Promise<void>((resolve) => httpServer.listen(0, '127.0.0.1', resolve));
  const address = httpServer.address();
  const port = typeof address === 'object' && address ? address.port : 0;
  baseHref = `mcp+http://localhost:${port}/mcp`;
});

after(async () => {
  await closeAllSessions();
  await transport.close();
  await new Promise<void>((resolve) => httpServer.close(() => resolve()));
});

/**
 * Builds a client with no security, as an unauthenticated MCP endpoint expects.
 */
function makeClient(): McpClient {
  const client = new McpClient();
  client.setSecurity([{ scheme: 'nosec' }] as SecurityScheme[]);
  return client;
}

test('invokes a tool over a real Streamable HTTP session', async () => {
  const client = makeClient();

  const result = await read(await client.invokeResource(form({ 'mcp:tool': 'greet' }), input({ name: 'ada' })));

  assert.equal(result.text, 'hello ada');
  assert.equal(result.type, 'text/plain');
});

test('reuses one session across calls and across clients', async () => {
  const first = makeClient();
  const second = makeClient();

  await first.invokeResource(form({ 'mcp:tool': 'greet' }), input({ name: 'grace' }));
  await first.invokeResource(form({ 'mcp:tool': 'greet' }), input({ name: 'alan' }));
  await second.invokeResource(form({ 'mcp:tool': 'greet' }), input({ name: 'edsger' }));

  // node-wot builds a client per consumed Thing, so pooling by endpoint plus credential
  // identity — rather than per client instance — is what keeps this at one connection.
  assert.equal(activeSessionCount(), 1);
});

test('reads a resource over the same transport', async () => {
  const client = makeClient();

  const result = await read(await client.readResource(form({ 'mcp:resource': 'file:///readme.txt' })));

  assert.equal(result.text, 'resource body');
  assert.equal(result.type, 'text/plain');
});

test('a tool-reported error raises instead of returning a payload', async () => {
  const client = makeClient();

  await assert.rejects(
    () => client.invokeResource(form({ 'mcp:tool': 'boom' }), input({})),
    (error: Error) => error.message.includes('boom') && error.message.includes('tool exploded'),
  );
});

test('describes itself as a Thing Description built from tools/list', async () => {
  const client = makeClient();
  const sessionsBefore = activeSessionCount();

  const described = await read(await client.requestThingDescription(baseHref));
  assert.equal(described.type, 'application/td+json');
  assert.equal(activeSessionCount(), sessionsBefore);

  const td = JSON.parse(described.text) as Record<string, any>;

  assert.equal(td.id, 'urn:mcp:wot-runtime-tests');
  assert.equal(td.title, 'wot-runtime-tests');

  // Both registered tools appear as actions, with forms pointing back at this binding.
  assert.deepEqual(Object.keys(td.actions).sort(), ['boom', 'greet']);
  assert.equal(td.actions.greet.forms[0].href, baseHref);
  assert.equal(td.actions.greet.forms[0]['mcp:tool'], 'greet');
  assert.equal(td.actions.greet.description, 'Greets someone');

  // The declared zod shape survives translation as a readable DataSchema.
  assert.equal(td.actions.greet.input.properties.name.type, 'string');

  // The registered resource becomes a read-only property.
  assert.equal(td.properties.readme.readOnly, true);
  assert.equal(td.properties.readme.forms[0]['mcp:resource'], 'file:///readme.txt');
});

test('a described endpoint can be invoked through the form it generated', async () => {
  const client = makeClient();

  const td = JSON.parse((await read(await client.requestThingDescription(baseHref))).text) as Record<string, any>;
  const generatedForm = td.actions.greet.forms[0] as Form;

  const result = await read(await client.invokeResource(generatedForm, input({ name: 'ada' })));

  assert.equal(result.text, 'hello ada');
});
