import assert from 'node:assert/strict';
import test from 'node:test';

import { buildCacheKey } from './cache.js';

test('buildCacheKey is stable for reordered object parameters', () => {
  const first = buildCacheKey(
    'thing:1',
    'invoke_action',
    'query',
    { range: { to: 20, from: 10 }, phase: 'a' },
    { filters: { unit: 'w', sensor: 'main' } },
  );
  const second = buildCacheKey(
    'thing:1',
    'invoke_action',
    'query',
    { phase: 'a', range: { from: 10, to: 20 } },
    { filters: { sensor: 'main', unit: 'w' } },
  );

  assert.equal(first, second);
});

test('buildCacheKey separates operations and affordances', () => {
  const uriVariables = { from: 10, to: 20 };

  assert.notEqual(
    buildCacheKey('thing:1', 'read_property', 'latest_power', uriVariables),
    buildCacheKey('thing:1', 'invoke_action', 'latest_power', uriVariables),
  );
  assert.notEqual(
    buildCacheKey('thing:1', 'read_property', 'latest_power', uriVariables),
    buildCacheKey('thing:1', 'read_property', 'latest_voltage', uriVariables),
  );
});
