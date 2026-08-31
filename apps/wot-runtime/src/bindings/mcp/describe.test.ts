import assert from 'node:assert/strict';
import test from 'node:test';

import { buildThingDescription } from './describe.js';

const HREF = 'mcp+http://127.0.0.1:55813/mcp';

/**
 * Builds a description input with sensible defaults for the field under test.
 */
function describeInput(overrides: Partial<Parameters<typeof buildThingDescription>[0]> = {}) {
  return buildThingDescription({
    href: HREF,
    serverName: 'server-everything',
    tools: [],
    resources: [],
    ...overrides,
  });
}

test('the document is a valid-shaped Thing Description', () => {
  const td = describeInput();

  assert.deepEqual(td['@context'], [
    'https://www.w3.org/2022/wot/td/v1.1',
    { mcp: 'https://modelcontextprotocol.io/specification#' },
  ]);
  assert.equal(td.id, 'urn:mcp:server-everything');
  assert.equal(td.title, 'server-everything');
  assert.deepEqual(td.security, ['nosec_sc']);
  assert.deepEqual(td.securityDefinitions, { nosec_sc: { scheme: 'nosec' } });
});

test('the id derives from the server name, not the endpoint', () => {
  // ToolHive assigns a new proxy port on restart, so an address-derived id would
  // change identity every time the server comes back.
  const first = describeInput({ href: 'mcp+http://127.0.0.1:1111/mcp' });
  const second = describeInput({ href: 'mcp+http://127.0.0.1:2222/mcp' });

  assert.equal(first.id, second.id);
});

test('a tool becomes an action whose form routes back to the MCP binding', () => {
  const td = describeInput({
    tools: [{ name: 'echo', description: 'Echoes input', inputSchema: { type: 'object' } }],
  });

  const actions = td.actions as Record<string, any>;
  assert.deepEqual(Object.keys(actions), ['echo']);
  assert.equal(actions.echo.description, 'Echoes input');
  assert.deepEqual(actions.echo.forms[0].op, ['invokeaction']);
  assert.equal(actions.echo.forms[0].href, HREF);
  assert.equal(actions.echo.forms[0]['mcp:tool'], 'echo');
});

test('the untranslated schema travels alongside the translated one', () => {
  const inputSchema = {
    type: 'object',
    properties: { where: { anyOf: [{ type: 'string' }, { type: 'null' }] } },
    additionalProperties: false,
  };
  const td = describeInput({ tools: [{ name: 'search', inputSchema }] });

  const action = (td.actions as Record<string, any>).search;

  // The action input is the closest DataSchema, so a reader sees real field names.
  assert.deepEqual(action.input, { type: 'object', properties: { where: { type: 'string' } } });
  // The original is preserved verbatim, since the translation cannot hold anyOf.
  assert.deepEqual(action.forms[0]['mcp:inputSchema'], inputSchema);
});

test('a tool with no schema gets no input rather than an empty object', () => {
  const td = describeInput({ tools: [{ name: 'ping' }] });

  assert.equal((td.actions as Record<string, any>).ping.input, undefined);
});

test('an output schema is carried when the server declares one', () => {
  const td = describeInput({
    tools: [{ name: 'weather', outputSchema: { type: 'object', properties: { temp: { type: 'number' } } } }],
  });

  assert.deepEqual((td.actions as Record<string, any>).weather.output, {
    type: 'object',
    properties: { temp: { type: 'number' } },
  });
});

test('hyphenated MCP tool names are kept as affordance names', () => {
  const td = describeInput({ tools: [{ name: 'get-tiny-image' }] });

  assert.ok('get-tiny-image' in (td.actions as Record<string, unknown>));
});

test('duplicate tool names are disambiguated rather than overwriting each other', () => {
  const td = describeInput({ tools: [{ name: 'search' }, { name: 'search' }] });

  assert.deepEqual(Object.keys(td.actions as Record<string, unknown>), ['search', 'search-2']);
});

test('a resource becomes a read-only property', () => {
  const td = describeInput({
    resources: [{ uri: 'file:///readme.txt', name: 'readme', mimeType: 'text/plain' }],
  });

  const properties = td.properties as Record<string, any>;
  assert.equal(properties.readme.readOnly, true);
  assert.deepEqual(properties.readme.forms[0].op, ['readproperty']);
  assert.equal(properties.readme.forms[0]['mcp:resource'], 'file:///readme.txt');
  assert.equal(properties.readme.forms[0].contentType, 'text/plain');
});

test('empty tool and resource lists produce no empty affordance maps', () => {
  const td = describeInput();

  assert.equal(td.actions, undefined);
  assert.equal(td.properties, undefined);
});

test('server instructions become the description when present', () => {
  const td = describeInput({ instructions: 'Use this server to fetch web pages.' });

  assert.equal(td.description, 'Use this server to fetch web pages.');
});

test('an unnamed server still produces a usable id', () => {
  const td = describeInput({ serverName: undefined });

  assert.equal(td.id, 'urn:mcp:mcp-server');
});
