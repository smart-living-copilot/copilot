import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildInternalHeaders,
  cleanupChatResourcesBatch,
  cleanupChatResources,
  deleteRemoteResource,
  selectChatsForBatchDeletion,
} from './chat-deletion';

test('buildInternalHeaders omits auth when no key is configured', () => {
  assert.equal(buildInternalHeaders(), undefined);
  assert.deepEqual(buildInternalHeaders('secret-key'), {
    Authorization: 'Bearer secret-key',
  });
});

test('deleteRemoteResource treats 404 as already deleted', async () => {
  const result = await deleteRemoteResource(
    'http://example.test/resource',
    undefined,
    'Example resource',
    async () => new Response(null, { status: 404 }),
  );

  assert.equal(result, null);
});

test('cleanupChatResources reports backend cleanup failures', async () => {
  const calls: Array<{ headers: HeadersInit | undefined; url: string }> = [];

  const failures = await cleanupChatResources({
    chatId: 'chat-123',
    wotbotUrl: 'http://wotbot.test',
    executorUrl: 'http://executor.test',
    internalApiKey: 'internal-secret',
    fetchImpl: async (url, init) => {
      calls.push({
        url: String(url),
        headers: init?.headers,
      });

      if (String(url).includes('/sessions/')) {
        return new Response(null, { status: 204 });
      }

      return new Response(null, { status: 500 });
    },
  });

  assert.deepEqual(failures, ['WoTBot thread cleanup failed (500)']);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0]?.headers, {
    Authorization: 'Bearer internal-secret',
  });
  assert.equal(calls[0]?.url, 'http://executor.test/sessions/chat-123');
  assert.equal(calls[1]?.url, 'http://wotbot.test/threads/chat-123');
});

test('selectChatsForBatchDeletion selects all chats', () => {
  const chats = [
    {
      id: 'chat-1',
      createdAt: '2026-01-01T10:00:00.000Z',
      updatedAt: '2026-01-02T10:00:00.000Z',
    },
    {
      id: 'chat-2',
      createdAt: '2026-01-03T10:00:00.000Z',
      updatedAt: '2026-01-04T10:00:00.000Z',
    },
  ];

  assert.deepEqual(
    selectChatsForBatchDeletion(chats, { mode: 'all' }).map((chat) => chat.id),
    ['chat-1', 'chat-2'],
  );
});

test('selectChatsForBatchDeletion filters by last updated date inclusively', () => {
  const chats = [
    {
      id: 'old-chat',
      createdAt: '2026-01-01T10:00:00.000Z',
      updatedAt: '2026-01-02T10:00:00.000Z',
    },
    {
      id: 'created-fallback',
      createdAt: '2026-01-02T10:00:00.000Z',
      updatedAt: null,
    },
    {
      id: 'new-chat',
      createdAt: '2026-01-01T10:00:00.000Z',
      updatedAt: '2026-01-03T10:00:00.000Z',
    },
    {
      id: 'invalid-date',
      createdAt: 'not-a-date',
      updatedAt: 'still-not-a-date',
    },
  ];

  assert.deepEqual(
    selectChatsForBatchDeletion(chats, {
      mode: 'before',
      before: '2026-01-02T10:00:00.000Z',
    }).map((chat) => chat.id),
    ['old-chat', 'created-fallback'],
  );
});

test('cleanupChatResourcesBatch preserves per-chat cleanup failures', async () => {
  const calls: string[] = [];

  const results = await cleanupChatResourcesBatch({
    chatIds: ['chat-1', 'chat-2'],
    wotbotUrl: 'http://wotbot.test',
    fetchImpl: async (url) => {
      calls.push(String(url));

      if (String(url).endsWith('/chat-2')) {
        return new Response(null, { status: 500 });
      }

      return new Response(null, { status: 204 });
    },
  });

  assert.deepEqual(results, [
    { chatId: 'chat-1', failures: [] },
    {
      chatId: 'chat-2',
      failures: ['WoTBot thread cleanup failed (500)'],
    },
  ]);
  assert.deepEqual(calls, [
    'http://wotbot.test/threads/chat-1',
    'http://wotbot.test/threads/chat-2',
  ]);
});
