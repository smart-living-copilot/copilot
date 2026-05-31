export const EMBED_EPHEMERAL_CHAT_ID_PREFIX = 'embed-ephemeral-';

export function createEmbedEphemeralChatId(): string {
  const suffix =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

  return `${EMBED_EPHEMERAL_CHAT_ID_PREFIX}${suffix}`;
}

export function isEmbedEphemeralChatId(chatId: string): boolean {
  return chatId.startsWith(EMBED_EPHEMERAL_CHAT_ID_PREFIX);
}
