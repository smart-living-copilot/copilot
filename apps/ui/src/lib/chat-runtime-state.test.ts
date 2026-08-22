import assert from 'node:assert/strict';
import test from 'node:test';

import { buildTextSubmission, type WotbotState } from './chat-runtime-state';

const initialValues: WotbotState = {
  messages: [
    { type: 'human', content: 'one', id: 'h1' },
    { type: 'ai', content: 'first answer', id: 'a1' },
  ],
};

test('preserves turns streamed since mount and appends the user turn optimistically', () => {
  const currentValues: WotbotState = {
    messages: [
      ...initialValues.messages,
      { type: 'human', content: 'two', id: 'h2' },
      { type: 'ai', content: 'second answer', id: 'a2' },
    ],
  };

  const submission = buildTextSubmission({
    currentValues,
    initialValues,
    messageId: 'h3',
    reasoningEffort: 'high',
    text: 'three',
  });

  assert.deepEqual(
    submission.optimisticValues.messages.map((message) => message.id),
    ['h1', 'a1', 'h2', 'a2', 'h3'],
  );
  assert.deepEqual(submission.input.messages, [
    { type: 'human', content: 'three', id: 'h3' },
  ]);
  assert.equal(submission.input.reasoning_effort, 'high');
  assert.equal(submission.optimisticValues.reasoning_effort, 'high');
});

test('falls back to loaded history before the stream has values', () => {
  const submission = buildTextSubmission({
    currentValues: {},
    initialValues,
    messageId: 'h2',
    text: 'two',
  });

  assert.deepEqual(
    submission.optimisticValues.messages.map((message) => message.id),
    ['h1', 'a1', 'h2'],
  );
});

test('rewinds optimistic history before an edited or retried turn', () => {
  const currentValues: WotbotState = {
    messages: [
      ...initialValues.messages,
      { type: 'human', content: 'two', id: 'h2' },
      { type: 'ai', content: 'second answer', id: 'a2' },
    ],
  };

  const submission = buildTextSubmission({
    currentValues,
    initialValues,
    messageId: 'replacement',
    replaceFromId: 'h2',
    text: 'edited two',
  });

  assert.deepEqual(
    submission.optimisticValues.messages.map((message) => message.id),
    ['h1', 'a1', 'replacement'],
  );
  assert.equal(
    submission.optimisticValues.messages.at(-1)?.content,
    'edited two',
  );
});
