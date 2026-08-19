import assert from 'node:assert/strict';
import test from 'node:test';

import {
  flattenUserMessageContent,
  hasEditableChange,
  messagesAfterEdit,
} from './chat-message-utils';

test('flattenUserMessageContent returns plain string content unchanged', () => {
  assert.equal(flattenUserMessageContent('hello there'), 'hello there');
});

test('flattenUserMessageContent joins text parts and drops non-text parts', () => {
  const content = flattenUserMessageContent([
    { type: 'text', text: 'first line' },
    { type: 'image_url' },
    { type: 'text', text: 'second line' },
  ]);

  assert.equal(content, 'first line\nsecond line');
});

test('flattenUserMessageContent treats missing content as empty', () => {
  assert.equal(flattenUserMessageContent(undefined), '');
});

test('messagesAfterEdit keeps the edited message id, only swapping its content', () => {
  // Load-bearing: the AG-UI/LangGraph bridge only recognizes this as an edit
  // (and forks/regenerates the checkpoint accordingly) when the id matches an
  // existing HumanMessage and the content differs. A new id here is silently
  // treated as an unrelated new message and the old turn never gets removed.
  const messages = [
    { id: 'human-1', role: 'user' as const, content: 'first question' },
    { id: 'ai-1', role: 'assistant' as const, content: 'first answer' },
    { id: 'human-2', role: 'user' as const, content: 'second question' },
    { id: 'ai-2', role: 'assistant' as const, content: 'second answer' },
  ];

  const result = messagesAfterEdit(messages, 'human-2', 'edited question');

  assert.equal(result.length, 3);
  assert.deepEqual(result.slice(0, 2), messages.slice(0, 2));
  assert.equal(result[2].id, 'human-2');
  assert.equal(result[2].role, 'user');
  assert.equal(result[2].content, 'edited question');
});

test('messagesAfterEdit drops messages after the edited one', () => {
  const messages = [
    { id: 'human-1', role: 'user' as const, content: 'first question' },
    { id: 'ai-1', role: 'assistant' as const, content: 'first answer' },
    { id: 'human-2', role: 'user' as const, content: 'second question' },
    { id: 'ai-2', role: 'assistant' as const, content: 'second answer' },
  ];

  const result = messagesAfterEdit(
    messages,
    'human-1',
    'edited first question',
  );

  assert.deepEqual(result, [
    { id: 'human-1', role: 'user', content: 'edited first question' },
  ]);
});

test('messagesAfterEdit falls back to appending a new message when the id is not found', () => {
  const messages = [
    { id: 'human-1', role: 'user' as const, content: 'first question' },
  ];

  const result = messagesAfterEdit(messages, 'missing-id', 'new content');

  assert.equal(result.length, 2);
  assert.deepEqual(result[0], messages[0]);
  assert.equal(result[1].content, 'new content');
  assert.notEqual(result[1].id, 'missing-id');
});

test('hasEditableChange is true when the draft differs from the original', () => {
  assert.equal(hasEditableChange('original text', 'edited text'), true);
});

test('hasEditableChange is false for an untouched draft', () => {
  // Saving this would submit a byte-identical HumanMessage. The backend's
  // edit detection is an exact string compare, so it wouldn't register as an
  // edit at all and would fall through to a duplicate-response bug instead
  // of a no-op -- this must be caught before the request goes out.
  assert.equal(hasEditableChange('original text', 'original text'), false);
});

test('hasEditableChange is false when the draft only adds surrounding whitespace', () => {
  assert.equal(hasEditableChange('original text', '  original text  '), false);
});

test('hasEditableChange is false for an empty or whitespace-only draft', () => {
  assert.equal(hasEditableChange('original text', ''), false);
  assert.equal(hasEditableChange('original text', '   '), false);
});

test('hasEditableChange treats non-text original content as different from any draft text', () => {
  assert.equal(
    hasEditableChange([{ type: 'image_url' }], 'a caption the image never had'),
    true,
  );
});
