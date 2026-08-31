import assert from 'node:assert/strict';
import test from 'node:test';

import { sessionKey } from './session.js';

test('the same endpoint and credentials share one session', () => {
  const headers = { Authorization: 'Bearer abc' };

  assert.equal(sessionKey('https://host/mcp', headers), sessionKey('https://host/mcp', { ...headers }));
});

test('header order does not change the session identity', () => {
  const first = sessionKey('https://host/mcp', { Authorization: 'Bearer abc', 'X-Tenant': 't1' });
  const second = sessionKey('https://host/mcp', { 'X-Tenant': 't1', Authorization: 'Bearer abc' });

  assert.equal(first, second);
});

test('different credentials against one endpoint do not share a session', () => {
  const first = sessionKey('https://host/mcp', { Authorization: 'Bearer abc' });
  const second = sessionKey('https://host/mcp', { Authorization: 'Bearer xyz' });

  assert.notEqual(first, second);
});

test('different endpoints do not share a session', () => {
  const headers = { Authorization: 'Bearer abc' };

  assert.notEqual(sessionKey('https://a/mcp', headers), sessionKey('https://b/mcp', headers));
});

test('unauthenticated endpoints pool under a shared anonymous identity', () => {
  assert.equal(sessionKey('https://host/mcp', {}), 'https://host/mcp#anonymous');
});

test('credential values never appear in the session key', () => {
  const key = sessionKey('https://host/mcp', { Authorization: 'Bearer super-secret-token' });

  assert.ok(!key.includes('super-secret-token'));
  assert.ok(!key.includes('Bearer'));
});
