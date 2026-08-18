import assert from 'node:assert/strict';
import test from 'node:test';

import {
  parseReasoningEffortLevels,
  resolveDefaultReasoningEffort,
  toReasoningEffortLabel,
} from './reasoning-effort';

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
