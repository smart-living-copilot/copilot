import assert from 'node:assert/strict';
import test from 'node:test';

import { fetchThreadState, loadSettledThreadState } from './thread-state';

test('fetchThreadState rejects non-success responses instead of returning empty history', async () => {
  await assert.rejects(
    fetchThreadState('thread/a', async () => new Response('', { status: 503 })),
    /Could not load conversation \(503\)/,
  );
});

test('loadSettledThreadState returns the newest snapshot after delayed persistence', async () => {
  const snapshots = [
    { values: { messages: [{ id: 'before' }] } },
    { values: { messages: [{ id: 'before' }, { id: 'after' }] } },
  ];
  const waits: number[] = [];
  let requestIndex = 0;

  const values = await loadSettledThreadState<{ messages: { id: string }[] }>(
    'thread/a',
    {
      delaysMs: [0, 250],
      fetcher: async (input) => {
        assert.equal(input, '/api/chat/thread%2Fa/state');
        const snapshot =
          snapshots[Math.min(requestIndex, snapshots.length - 1)];
        requestIndex += 1;
        return Response.json(snapshot);
      },
      wait: async (delayMs) => {
        waits.push(delayMs);
      },
    },
  );

  assert.deepEqual(
    values.messages.map((message) => message.id),
    ['before', 'after'],
  );
  assert.deepEqual(waits, [250]);
});

test('loadSettledThreadState tolerates a transient failed read', async () => {
  let requestIndex = 0;
  const values = await loadSettledThreadState<{ messages: unknown[] }>('t1', {
    delaysMs: [0, 1],
    fetcher: async () => {
      requestIndex += 1;
      return requestIndex === 1
        ? new Response('', { status: 503 })
        : Response.json({ values: { messages: [] } });
    },
    wait: async () => {},
  });

  assert.deepEqual(values, { messages: [] });
});
