import assert from 'node:assert/strict';
import test from 'node:test';

import { unwrapRuntimeResult } from './use-wot-bridge';

test('unwrapRuntimeResult returns inline payload data directly', () => {
  assert.deepEqual(
    unwrapRuntimeResult({
      result: {
        success: true,
        payload: {
          kind: 'inline',
          content_type: 'application/json',
          data: { temperature: 21 },
        },
      },
    }),
    { ok: true, value: { temperature: 21 } },
  );
});

test('unwrapRuntimeResult normalizes runtime binary payload envelopes', () => {
  assert.deepEqual(
    unwrapRuntimeResult({
      result: {
        success: true,
        payload: {
          kind: 'binary',
          content_type: 'image/png',
          body_base64: 'aGVsbG8=',
          size_bytes: 5,
        },
      },
    }),
    {
      ok: true,
      value: {
        kind: 'binary',
        contentType: 'image/png',
        bodyBase64: 'aGVsbG8=',
        sizeBytes: 5,
      },
    },
  );
});

test('unwrapRuntimeResult keeps camelCase binary action results intact', () => {
  assert.deepEqual(
    unwrapRuntimeResult({
      outcome: 'completed_result',
      completed_result: {
        success: true,
        payload: {
          kind: 'binary',
          contentType: 'application/octet-stream',
          bodyBase64: '',
          sizeBytes: 0,
        },
      },
    }),
    {
      ok: true,
      value: {
        kind: 'binary',
        contentType: 'application/octet-stream',
        bodyBase64: '',
        sizeBytes: 0,
      },
    },
  );
});

test('unwrapRuntimeResult preserves runtime errors', () => {
  assert.deepEqual(
    unwrapRuntimeResult({
      result: {
        success: false,
        status_text: 'Unsupported media type',
      },
    }),
    { ok: false, error: 'Unsupported media type' },
  );
});
