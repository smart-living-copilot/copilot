import assert from 'node:assert/strict';
import test from 'node:test';

import { canaryEventBindings, errorDetail } from './manager.js';
import type { VirtualThingDefinition } from './types.js';

test('canaryEventBindings dry-runs emitted events without requiring real emission', async () => {
  const calls: unknown[][] = [];
  const definition: VirtualThingDefinition = {
    id: 'virtual:things:counter',
    title: 'Counter',
    description: '',
    td: {},
    version: 1,
    status: 'active',
    bindings: [
      {
        affordance_type: 'event',
        affordance_name: 'tick',
        kind: 'emitted',
        trigger: { kind: 'interval', interval_seconds: 10 },
      },
      {
        affordance_type: 'property',
        affordance_name: 'ignored',
        kind: 'computed',
      },
    ],
  };

  await canaryEventBindings(definition, async (...args) => {
    calls.push(args);
    return null;
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'virtual:things:counter');
  assert.equal(calls[0][1], 'tick');
  assert.deepEqual(calls[0][3], { dryRun: true });
});

test('errorDetail includes axios response body', () => {
  const error = Object.assign(new Error('Request failed'), {
    response: { data: { detail: 'handler failed' } },
  });

  assert.match(errorDetail(error), /handler failed/);
});
