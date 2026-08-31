import assert from 'node:assert/strict';
import test from 'node:test';

import {
  findConfigMismatches,
  findField,
  formatConfigValue,
  type ConfigField,
  type ConfigReport,
} from './config-report';
import type { ReasoningEffortConfig } from './reasoning-effort';

function field(
  overrides: Partial<ConfigField> & { name: string },
): ConfigField {
  return {
    value: null,
    configured: false,
    is_default: false,
    secret: false,
    note: null,
    ...overrides,
  };
}

function report(fields: ConfigField[]): ConfigReport {
  return {
    version: '0.1.1',
    sections: [{ key: 'reasoning', title: 'Reasoning effort', fields }],
  };
}

function uiConfig(
  overrides: Partial<ReasoningEffortConfig> = {},
): ReasoningEffortConfig {
  return {
    enabled: true,
    levels: ['low', 'high'],
    defaultLevel: 'low',
    ...overrides,
  };
}

test('findField locates a field across sections', () => {
  const multi: ConfigReport = {
    version: '0.1.1',
    sections: [
      { key: 'a', title: 'A', fields: [field({ name: 'ONE' })] },
      { key: 'b', title: 'B', fields: [field({ name: 'TWO', value: 2 })] },
    ],
  };

  assert.equal(findField(multi, 'TWO')?.value, 2);
  assert.equal(findField(multi, 'MISSING'), null);
});

test('matching reasoning-effort config reports no mismatch', () => {
  const mismatches = findConfigMismatches(
    report([
      field({ name: 'REASONING_EFFORT_ENABLED', value: true }),
      field({ name: 'REASONING_EFFORT_LEVELS', value: 'low,high' }),
    ]),
    uiConfig(),
  );

  assert.deepEqual(mismatches, []);
});

test('a backend that disabled reasoning effort is flagged', () => {
  const mismatches = findConfigMismatches(
    report([
      field({ name: 'REASONING_EFFORT_ENABLED', value: false }),
      field({ name: 'REASONING_EFFORT_LEVELS', value: 'low,high' }),
    ]),
    uiConfig(),
  );

  assert.equal(mismatches.length, 1);
  assert.equal(mismatches[0].setting, 'REASONING_EFFORT_ENABLED');
  assert.equal(mismatches[0].uiValue, 'true');
  assert.equal(mismatches[0].backendValue, 'false');
});

test('levels the agent will not honour are flagged', () => {
  const mismatches = findConfigMismatches(
    report([
      field({ name: 'REASONING_EFFORT_ENABLED', value: true }),
      field({ name: 'REASONING_EFFORT_LEVELS', value: 'low,medium,high' }),
    ]),
    uiConfig(),
  );

  assert.equal(mismatches.length, 1);
  assert.equal(mismatches[0].setting, 'REASONING_EFFORT_LEVELS');
  assert.equal(mismatches[0].uiValue, 'low, high');
  assert.equal(mismatches[0].backendValue, 'low, medium, high');
});

test('level ordering differences are flagged, since the first level is the default', () => {
  const mismatches = findConfigMismatches(
    report([field({ name: 'REASONING_EFFORT_LEVELS', value: 'high,low' })]),
    uiConfig({ levels: ['low', 'high'] }),
  );

  assert.equal(mismatches.length, 1);
  assert.equal(mismatches[0].setting, 'REASONING_EFFORT_LEVELS');
});

test('backend whitespace in the level list is not a mismatch', () => {
  const mismatches = findConfigMismatches(
    report([field({ name: 'REASONING_EFFORT_LEVELS', value: ' low , high ' })]),
    uiConfig(),
  );

  assert.deepEqual(mismatches, []);
});

test('an absent field is not compared', () => {
  assert.deepEqual(findConfigMismatches(report([]), uiConfig()), []);
});

test('formatConfigValue renders empty and false values distinctly', () => {
  assert.equal(formatConfigValue(field({ name: 'A', value: '' })), 'not set');
  assert.equal(formatConfigValue(field({ name: 'B', value: null })), 'not set');
  assert.equal(formatConfigValue(field({ name: 'C', value: false })), 'false');
  assert.equal(formatConfigValue(field({ name: 'D', value: 0 })), '0');
  assert.equal(
    formatConfigValue(
      field({ name: 'E', value: '•••••••• (set)', secret: true }),
    ),
    '•••••••• (set)',
  );
});
