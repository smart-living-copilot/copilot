import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildInternalHeaders,
  cleanupChatResources,
  deleteRemoteResource,
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
    copilotUrl: 'http://copilot.test',
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

  assert.deepEqual(failures, ['Copilot thread cleanup failed (500)']);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0]?.headers, {
    Authorization: 'Bearer internal-secret',
  });
  assert.equal(calls[0]?.url, 'http://executor.test/sessions/chat-123');
  assert.equal(calls[1]?.url, 'http://copilot.test/threads/chat-123');
});
