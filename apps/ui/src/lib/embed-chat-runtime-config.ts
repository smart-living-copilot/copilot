export const EMBED_CHAT_ALLOWED_ORIGINS_ENV = 'EMBED_CHAT_ALLOWED_ORIGINS';

function normalizeAllowedOrigin(value: string): string | null {
  if (value === '*' || value === 'null') {
    return null;
  }

  try {
    const url = new URL(value);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return null;
    }

    return url.origin;
  } catch {
    return null;
  }
}

export function parseEmbedChatAllowedOrigins(rawValue: string | undefined) {
  if (!rawValue) {
    return [];
  }

  const origins = new Set<string>();
  for (const entry of rawValue.split(',')) {
    const origin = normalizeAllowedOrigin(entry.trim());
    if (origin) {
      origins.add(origin);
    }
  }

  return [...origins].sort();
}

export function getEmbedChatAllowedOrigins() {
  return parseEmbedChatAllowedOrigins(
    process.env[EMBED_CHAT_ALLOWED_ORIGINS_ENV],
  );
}
