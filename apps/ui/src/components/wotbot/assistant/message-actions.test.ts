import assert from 'node:assert/strict';
import test from 'node:test';

import {
  findRetryTarget,
  hasAssistantReloadAction,
  hasAssistantResponseActions,
} from './message-actions';

const state = (
  content: Array<{ type: string; text?: string }>,
  status = 'complete',
) => ({ message: { content, status: { type: status } } });

test('shows actions for a completed textual response', () => {
  assert.equal(
    hasAssistantResponseActions(state([{ type: 'text', text: 'Done.' }])),
    true,
  );
});

test('hides actions for tool groups and interaction summaries', () => {
  assert.equal(
    hasAssistantResponseActions(state([{ type: 'tool-call' }])),
    false,
  );
});

test('hides actions for a preamble that also starts a tool call', () => {
  assert.equal(
    hasAssistantResponseActions(
      state([
        { type: 'text', text: 'Let me look that up.' },
        { type: 'tool-call' },
      ]),
    ),
    false,
  );
});

test('hides actions for reasoning-only, blank, and running messages', () => {
  assert.equal(
    hasAssistantResponseActions(
      state([{ type: 'reasoning', text: 'internal' }]),
    ),
    false,
  );
  assert.equal(
    hasAssistantResponseActions(state([{ type: 'text', text: '   ' }])),
    false,
  );
  assert.equal(
    hasAssistantResponseActions(
      state([{ type: 'text', text: 'Streaming' }], 'running'),
    ),
    false,
  );
});

test('only shows reload when the runtime supports it', () => {
  const message = state([{ type: 'text', text: 'Done.' }]).message;

  assert.equal(
    hasAssistantReloadAction({
      message,
      thread: { capabilities: { reload: true } },
    }),
    true,
  );
  assert.equal(
    hasAssistantReloadAction({
      message,
      thread: { capabilities: { reload: false } },
    }),
    false,
  );
});

test('retry resolves the user turn behind intervening tool groups', () => {
  assert.deepEqual(
    findRetryTarget(
      [
        {
          id: 'user-1',
          role: 'user',
          content: [{ type: 'text', text: 'What do I own?' }],
        },
        {
          id: 'tools-1',
          role: 'assistant',
          content: [{ type: 'tool-call' }],
        },
        {
          id: 'answer-1',
          role: 'assistant',
          content: [{ type: 'text', text: 'Three things.' }],
        },
      ],
      'tools-1',
    ),
    { sourceId: 'user-1', text: 'What do I own?' },
  );
});

test('retry returns null when its parent is unknown', () => {
  assert.equal(
    findRetryTarget(
      [
        {
          id: 'user-1',
          role: 'user',
          content: [{ type: 'text', text: 'Hello' }],
        },
      ],
      'missing',
    ),
    null,
  );
});

test('retry accepts legacy string user content', () => {
  assert.deepEqual(
    findRetryTarget(
      [{ id: 'user-1', role: 'user', content: '  Try again  ' }],
      'user-1',
    ),
    { sourceId: 'user-1', text: 'Try again' },
  );
});
