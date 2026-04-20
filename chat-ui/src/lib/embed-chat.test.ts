import assert from 'node:assert/strict';
import test from 'node:test';

import {
  EMBED_EPHEMERAL_CHAT_ID_PREFIX,
  createEmbedEphemeralChatId,
  isEmbedEphemeralChatId,
} from './embed-chat';

test('createEmbedEphemeralChatId prefixes embed chat ids', () => {
  const chatId = createEmbedEphemeralChatId();

  assert.ok(chatId.startsWith(EMBED_EPHEMERAL_CHAT_ID_PREFIX));
  assert.equal(isEmbedEphemeralChatId(chatId), true);
});

test('isEmbedEphemeralChatId rejects persisted chat ids', () => {
  assert.equal(isEmbedEphemeralChatId('chat-123'), false);
});
