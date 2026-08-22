import assert from 'node:assert/strict';
import test from 'node:test';

import {
  isReasoningEffortSelectorEnabled,
  makeReasoningEffortOptions,
  parseReasoningEffortLevels,
  resolveDefaultReasoningEffort,
  resolveStoredReasoningEffort,
  toReasoningEffortLabel,
} from './reasoning-effort';
import { getReasoningEffortRuntimeConfig } from './reasoning-effort-runtime-config';

test('parseReasoningEffortLevels trims, dedupes, and drops empties', () => {
  assert.deepEqual(parseReasoningEffortLevels(' low, medium ,high ,low,'), [
    'low',
    'medium',
    'high',
  ]);
});

test('parseReasoningEffortLevels returns empty for unset input', () => {
  assert.deepEqual(parseReasoningEffortLevels(undefined), []);
  assert.deepEqual(parseReasoningEffortLevels(''), []);
});

test('toReasoningEffortLabel capitalizes the level', () => {
  assert.equal(toReasoningEffortLabel('medium'), 'Medium');
  assert.equal(toReasoningEffortLabel(''), '');
});

test('makeReasoningEffortOptions creates labels for configured levels', () => {
  assert.deepEqual(makeReasoningEffortOptions(['none', 'high']), [
    { label: 'None', value: 'none' },
    { label: 'High', value: 'high' },
  ]);
});

test('resolveDefaultReasoningEffort prefers a requested level that is allowed', () => {
  assert.equal(
    resolveDefaultReasoningEffort(['low', 'medium', 'high'], 'high'),
    'high',
  );
});

test('resolveDefaultReasoningEffort falls back to the first level otherwise', () => {
  assert.equal(
    resolveDefaultReasoningEffort(['low', 'medium', 'high'], 'extreme'),
    'low',
  );
  assert.equal(
    resolveDefaultReasoningEffort(['low', 'medium', 'high'], undefined),
    'low',
  );
});

test('resolveDefaultReasoningEffort returns null when there are no levels', () => {
  assert.equal(resolveDefaultReasoningEffort([], 'high'), null);
});

test('resolveStoredReasoningEffort prefers a stored value that is still allowed', () => {
  assert.equal(
    resolveStoredReasoningEffort(['low', 'medium', 'high'], 'high', 'low'),
    'high',
  );
});

test('resolveStoredReasoningEffort falls back when the stored value is missing or stale', () => {
  assert.equal(
    resolveStoredReasoningEffort(['low', 'medium', 'high'], null, 'low'),
    'low',
  );
  assert.equal(
    resolveStoredReasoningEffort(['low', 'medium', 'high'], 'extreme', 'low'),
    'low',
  );
});

test('runtime config reads the backend reasoning-effort environment', () => {
  const config = getReasoningEffortRuntimeConfig({
    REASONING_EFFORT_ENABLED: 'true',
    REASONING_EFFORT_LEVELS: ' none, think ',
    REASONING_EFFORT_DEFAULT: 'think',
  });

  assert.deepEqual(config, {
    enabled: true,
    levels: ['none', 'think'],
    defaultLevel: 'think',
  });
  assert.equal(isReasoningEffortSelectorEnabled(config), true);
});

test('runtime config is disabled by default and keeps backend default levels', () => {
  const config = getReasoningEffortRuntimeConfig({});

  assert.deepEqual(config, {
    enabled: false,
    levels: ['low', 'medium', 'high'],
    defaultLevel: 'low',
  });
  assert.equal(isReasoningEffortSelectorEnabled(config), false);
});

test('runtime config preserves an explicitly empty level list', () => {
  assert.deepEqual(
    getReasoningEffortRuntimeConfig({
      REASONING_EFFORT_ENABLED: 'true',
      REASONING_EFFORT_LEVELS: '',
    }),
    {
      enabled: true,
      levels: [],
      defaultLevel: null,
    },
  );
});
