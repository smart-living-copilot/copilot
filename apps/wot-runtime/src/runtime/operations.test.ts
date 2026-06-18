import assert from 'node:assert/strict';
import test from 'node:test';

import { isCacheableSafeAction, missingInvokeActionInputMessage, resolveInvokeActionInput } from './operations.js';

test('resolveInvokeActionInput defaults missing optional object input to empty object', () => {
  const actionDef = {
    input: {
      type: 'object',
      properties: {
        from_ms: { type: 'integer' },
        to_ms: { type: 'integer' },
      },
    },
  };

  assert.deepEqual(resolveInvokeActionInput(actionDef, undefined), {});
  assert.deepEqual(resolveInvokeActionInput(actionDef, null), {});
});

test('resolveInvokeActionInput preserves provided input values', () => {
  const actionDef = {
    input: {
      type: 'object',
      properties: {
        from_ms: { type: 'integer' },
      },
    },
  };

  assert.deepEqual(resolveInvokeActionInput(actionDef, { from_ms: 123 }), { from_ms: 123 });
});

test('missingInvokeActionInputMessage explains required object input', () => {
  const actionDef = {
    input: {
      type: 'object',
      required: ['from_ms', 'to_ms'],
      properties: {
        from_ms: { type: 'integer' },
        to_ms: { type: 'integer' },
      },
    },
  };

  assert.equal(
    missingInvokeActionInputMessage(actionDef, 'virtual:things:energy', 'analyze', undefined),
    "InvokeAction input for 'virtual:things:energy/analyze' must be an object with required fields: from_ms, to_ms. Pass an object matching the Thing Description input schema.",
  );
});

test('missingInvokeActionInputMessage ignores optional object input', () => {
  const actionDef = {
    input: {
      type: 'object',
      properties: {
        from_ms: { type: 'integer' },
      },
    },
  };

  assert.equal(missingInvokeActionInputMessage(actionDef, 'virtual:things:energy', 'analyze', undefined), null);
});

test('isCacheableSafeAction only accepts explicit safe actions', () => {
  assert.equal(isCacheableSafeAction({ safe: true }), true);
  assert.equal(isCacheableSafeAction({ safe: false }), false);
  assert.equal(isCacheableSafeAction({}), false);
  assert.equal(isCacheableSafeAction(null), false);
});
