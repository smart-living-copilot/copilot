import assert from 'node:assert/strict';
import test from 'node:test';
import {
  isSnapshotRequestTooLarge,
  serializeSnapshotMessages,
} from './chat-snapshots';

test('serializeSnapshotMessages trims unsupported fields and large payloads', () => {
  const result = serializeSnapshotMessages([
    {
      id: 'assistant-1',
      role: 'assistant',
      content: 'hello',
      generativeUI: () => 'drop me',
      toolCalls: [
        {
          id: 'tool-1',
          type: 'function',
          function: {
            name: 'run_code',
            arguments: JSON.stringify({
              nested: {
                keep: 'value',
              },
              huge: 'x'.repeat(20_000),
            }),
          },
        },
      ],
    },
    {
      id: 'tool-message',
      role: 'tool',
      toolCallId: 'tool-1',
      content: JSON.stringify({
        stdout: 'ok',
        huge: 'y'.repeat(20_000),
      }),
    },
    {
      id: 'user-1',
      role: 'user',
      content: [
        { type: 'text', text: 'show me the result' },
        {
          type: 'binary',
          mimeType: 'image/png',
          filename: 'preview.png',
          data: 'very-large-inline-binary-that-should-not-persist',
        },
      ],
    },
  ]);

  assert.equal(result.messages.length, 3);
  assert.ok(result.json.length > 0);
  assert.ok(result.json.length < 256_000);

  const assistant = result.messages[0];
  assert.equal(assistant?.role, 'assistant');
  assert.ok(assistant && 'toolCalls' in assistant);
  assert.equal(assistant.toolCalls?.[0]?.function.name, 'run_code');
  assert.ok(assistant.toolCalls?.[0]?.function.arguments.includes('nested'));
  assert.equal(
    'generativeUI' in assistant ? assistant.generativeUI : undefined,
    undefined,
  );

  const user = result.messages[2];
  assert.equal(user?.role, 'user');
  assert.ok(Array.isArray(user?.content));
  assert.deepEqual(user.content?.[1], {
    type: 'binary',
    mimeType: 'image/png',
    filename: 'preview.png',
  });
});

test('serializeSnapshotMessages keeps only the newest messages within budget', () => {
  const oversizedMessages = Array.from({ length: 120 }, (_, index) => ({
    id: `message-${index}`,
    role: 'assistant' as const,
    content: `message-${index}`,
  }));

  const result = serializeSnapshotMessages(oversizedMessages);

  assert.equal(result.messages.length, 80);
  assert.equal(result.messages[0]?.id, 'message-40');
  assert.equal(result.messages.at(-1)?.id, 'message-119');
});

test('isSnapshotRequestTooLarge rejects oversized request bodies', () => {
  const rawBody = JSON.stringify({
    messages: [
      {
        id: 'message-1',
        role: 'assistant',
        content: 'z'.repeat(400_000),
      },
    ],
  });

  assert.equal(isSnapshotRequestTooLarge(rawBody), true);
  assert.equal(
    isSnapshotRequestTooLarge(
      JSON.stringify({
        messages: [{ id: 'message-1', role: 'assistant', content: 'ok' }],
      }),
    ),
    false,
  );
});
