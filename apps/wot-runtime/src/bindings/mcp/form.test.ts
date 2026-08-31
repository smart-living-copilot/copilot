import assert from 'node:assert/strict';
import test from 'node:test';

import type { Form } from '@node-wot/core';

import {
  getMcpResourceUri,
  getMcpToolName,
  requireMcpResourceUri,
  requireMcpToolName,
  resolveMcpEndpoint,
} from './form.js';

/**
 * Builds a minimal form object with arbitrary extension fields.
 */
function makeForm(fields: Record<string, unknown>): Form {
  return { href: 'mcp+https://example.com/mcp', ...fields } as unknown as Form;
}

test('getMcpToolName reads the tool name from a form', () => {
  assert.equal(getMcpToolName(makeForm({ 'mcp:tool': 'search' })), 'search');
});

test('getMcpToolName trims surrounding whitespace', () => {
  assert.equal(getMcpToolName(makeForm({ 'mcp:tool': '  search  ' })), 'search');
});

test('getMcpToolName returns null when the field is absent, blank, or not a string', () => {
  assert.equal(getMcpToolName(makeForm({})), null);
  assert.equal(getMcpToolName(makeForm({ 'mcp:tool': '   ' })), null);
  assert.equal(getMcpToolName(makeForm({ 'mcp:tool': 42 })), null);
});

test('requireMcpToolName names the missing field so the TD can be fixed', () => {
  assert.throws(
    () => requireMcpToolName(makeForm({})),
    (error: Error) => error.message.includes('mcp:tool'),
  );
});

test('getMcpResourceUri reads the resource URI from a form', () => {
  assert.equal(getMcpResourceUri(makeForm({ 'mcp:resource': 'file:///data.json' })), 'file:///data.json');
});

test('requireMcpResourceUri names the missing field', () => {
  assert.throws(
    () => requireMcpResourceUri(makeForm({})),
    (error: Error) => error.message.includes('mcp:resource'),
  );
});

test('resolveMcpEndpoint strips the mcp+ prefix and keeps port, path and query', () => {
  assert.equal(resolveMcpEndpoint('mcp+https://host:8080/mcp?v=1'), 'https://host:8080/mcp?v=1');
  assert.equal(resolveMcpEndpoint('mcp+http://localhost:3000/mcp'), 'http://localhost:3000/mcp');
});

test('resolveMcpEndpoint preserves userinfo rather than rebuilding the URL', () => {
  assert.equal(resolveMcpEndpoint('mcp+https://user:pw@host/mcp'), 'https://user:pw@host/mcp');
});

test('resolveMcpEndpoint rejects an href without the mcp+ prefix', () => {
  assert.throws(
    () => resolveMcpEndpoint('https://host/mcp'),
    (error: Error) => error.message.includes('mcp+'),
  );
});

test('resolveMcpEndpoint rejects an unsupported transport', () => {
  assert.throws(
    () => resolveMcpEndpoint('mcp+ftp://host/mcp'),
    (error: Error) => error.message.includes('not supported'),
  );
});

test('resolveMcpEndpoint rejects a missing or malformed href', () => {
  assert.throws(() => resolveMcpEndpoint(undefined));
  assert.throws(() => resolveMcpEndpoint('   '));
  assert.throws(() => resolveMcpEndpoint('mcp+https://'));
});
