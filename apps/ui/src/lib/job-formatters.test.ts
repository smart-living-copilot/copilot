import assert from 'node:assert/strict';
import test from 'node:test';

import { getSubmittedRecordResultSummary } from './job-formatters';

test('getSubmittedRecordResultSummary summarizes submitted record data', () => {
  assert.equal(
    getSubmittedRecordResultSummary({
      submitted_record: {
        data: {
          mood: 'good',
          energy: 4,
          note: 'slept well',
        },
      },
    }),
    'Structured record: mood=good, energy=4, note=slept well',
  );
});

test('getSubmittedRecordResultSummary ignores non-record results', () => {
  assert.equal(getSubmittedRecordResultSummary({ ok: true }), null);
});
