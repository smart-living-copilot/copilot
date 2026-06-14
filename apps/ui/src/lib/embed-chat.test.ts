import assert from 'node:assert/strict';
import test from 'node:test';

import {
  EMBED_EPHEMERAL_CHAT_ID_PREFIX,
  EMBED_PREFILL_MAX_PROMPT_LENGTH,
  createEmbedEphemeralChatId,
  isEmbedAutosubmitValue,
  isEmbedEphemeralChatId,
  normalizeEmbedPrefillPrompt,
} from './embed-chat';
import { parseEmbedChatAllowedOrigins } from './embed-chat-runtime-config';
import { getEmbedInitialPrefillFromSearchParams } from './embed-chat-search-params';

test('createEmbedEphemeralChatId prefixes embed chat ids', () => {
  const chatId = createEmbedEphemeralChatId();

  assert.ok(chatId.startsWith(EMBED_EPHEMERAL_CHAT_ID_PREFIX));
  assert.equal(isEmbedEphemeralChatId(chatId), true);
});

test('isEmbedEphemeralChatId rejects persisted chat ids', () => {
  assert.equal(isEmbedEphemeralChatId('chat-123'), false);
});

test('normalizeEmbedPrefillPrompt trims and caps prompt text', () => {
  assert.equal(normalizeEmbedPrefillPrompt('  hello deck  '), 'hello deck');
  assert.equal(normalizeEmbedPrefillPrompt('   '), null);
  assert.equal(normalizeEmbedPrefillPrompt(null), null);

  const oversizedPrompt = 'x'.repeat(EMBED_PREFILL_MAX_PROMPT_LENGTH + 1);
  assert.equal(
    normalizeEmbedPrefillPrompt(oversizedPrompt)?.length,
    EMBED_PREFILL_MAX_PROMPT_LENGTH,
  );
});

test('isEmbedAutosubmitValue recognizes explicit truthy values', () => {
  assert.equal(isEmbedAutosubmitValue('1'), true);
  assert.equal(isEmbedAutosubmitValue('true'), true);
  assert.equal(isEmbedAutosubmitValue('yes'), true);
  assert.equal(isEmbedAutosubmitValue('on'), true);
  assert.equal(isEmbedAutosubmitValue('0'), false);
  assert.equal(isEmbedAutosubmitValue(null), false);
});

test('getEmbedInitialPrefillFromSearchParams parses prompt and autosubmit', () => {
  assert.deepEqual(
    getEmbedInitialPrefillFromSearchParams({
      autosubmit: '1',
      prompt: '  Show the lights  ',
    }),
    {
      prompt: 'Show the lights',
      submit: true,
    },
  );
});

test('getEmbedInitialPrefillFromSearchParams ignores missing prompts', () => {
  assert.equal(
    getEmbedInitialPrefillFromSearchParams({ autosubmit: '1' }),
    null,
  );
});

test('parseEmbedChatAllowedOrigins normalizes exact http origins', () => {
  assert.deepEqual(
    parseEmbedChatAllowedOrigins(
      'https://deck.example/presenter, http://localhost:8080/path',
    ),
    ['http://localhost:8080', 'https://deck.example'],
  );
});

test('parseEmbedChatAllowedOrigins rejects broad or invalid origins', () => {
  assert.deepEqual(
    parseEmbedChatAllowedOrigins(
      '*, null, file:///tmp/deck.html, notaurl, ftp://deck.example',
    ),
    [],
  );
});
