export const EMBED_EPHEMERAL_CHAT_ID_PREFIX = 'embed-ephemeral-';
export const EMBED_PREFILL_MAX_PROMPT_LENGTH = 8000;

export interface EmbedChatPrefill {
  prompt: string;
  submit: boolean;
}

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

export function normalizeEmbedPrefillPrompt(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }

  const prompt = value.slice(0, EMBED_PREFILL_MAX_PROMPT_LENGTH).trim();
  return prompt || null;
}

export function isEmbedAutosubmitValue(value: string | null): boolean {
  return (
    value !== null && ['1', 'true', 'yes', 'on'].includes(value.toLowerCase())
  );
}

export function isEmbedDisabledValue(value: string | null): boolean {
  return (
    value !== null && ['0', 'false', 'no', 'off'].includes(value.toLowerCase())
  );
}
