import assert from 'node:assert/strict';
import test from 'node:test';

import {
  EMBED_EPHEMERAL_CHAT_ID_PREFIX,
  EMBED_PREFILL_MAX_PROMPT_LENGTH,
  createEmbedEphemeralChatId,
  isEmbedAutosubmitValue,
  isEmbedDisabledValue,
  isEmbedEphemeralChatId,
  normalizeEmbedPrefillPrompt,
} from './embed-chat';
import { parseEmbedChatAllowedOrigins } from './embed-chat-runtime-config';
import {
  areEmbedExamplesEnabledFromSearchParams,
  areEmbedJobEventsEnabledFromSearchParams,
  getEmbedInitialPrefillFromSearchParams,
  getEmbedThemeFromSearchParams,
} from './embed-chat-search-params';

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

test('isEmbedDisabledValue recognizes explicit disabled values', () => {
  assert.equal(isEmbedDisabledValue('0'), true);
  assert.equal(isEmbedDisabledValue('false'), true);
  assert.equal(isEmbedDisabledValue('no'), true);
  assert.equal(isEmbedDisabledValue('off'), true);
  assert.equal(isEmbedDisabledValue('1'), false);
  assert.equal(isEmbedDisabledValue(null), false);
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

test('embed search params can disable examples and job events', () => {
  assert.equal(areEmbedExamplesEnabledFromSearchParams({}), true);
  assert.equal(
    areEmbedExamplesEnabledFromSearchParams({ examples: '0' }),
    false,
  );
  assert.equal(areEmbedJobEventsEnabledFromSearchParams({}), true);
  assert.equal(
    areEmbedJobEventsEnabledFromSearchParams({ jobEvents: 'off' }),
    false,
  );
});

test('getEmbedThemeFromSearchParams accepts supported theme values', () => {
  assert.equal(getEmbedThemeFromSearchParams({ theme: 'light' }), 'light');
  assert.equal(getEmbedThemeFromSearchParams({ theme: 'DARK' }), 'dark');
  assert.equal(getEmbedThemeFromSearchParams({ theme: ' system ' }), 'system');
  assert.equal(
    getEmbedThemeFromSearchParams({ theme: ['dark', 'light'] }),
    'dark',
  );
});

test('getEmbedThemeFromSearchParams ignores unsupported theme values', () => {
  assert.equal(getEmbedThemeFromSearchParams({}), null);
  assert.equal(getEmbedThemeFromSearchParams({ theme: 'auto' }), null);
  assert.equal(getEmbedThemeFromSearchParams({ theme: '' }), null);
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
