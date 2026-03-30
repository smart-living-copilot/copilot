import type { Message } from '@copilotkit/shared';

const textEncoder = new TextEncoder();

export const MAX_SNAPSHOT_REQUEST_BYTES = 384_000;
const MAX_SNAPSHOT_BYTES = 256_000;
const MAX_SNAPSHOT_MESSAGES = 80;
const MAX_STRING_LENGTH = 4_000;
const MAX_TOOL_STRING_LENGTH = 12_000;
const MAX_ARRAY_ITEMS = 20;
const MAX_OBJECT_KEYS = 24;
const MAX_TOOL_CALLS = 8;
const MAX_DEPTH = 6;

type JsonValue =
  | boolean
  | null
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

type SanitizedUserContentItem =
  | {
      type: 'text';
      text: string;
    }
  | {
      type: 'binary';
      mimeType: string;
      filename?: string;
      id?: string;
      url?: string;
    };

function byteLength(value: string) {
  return textEncoder.encode(value).length;
}

function truncateString(value: string, maxLength = MAX_STRING_LENGTH) {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, Math.max(0, maxLength - 3))}...`;
}

function sanitizeJsonValue(
  value: unknown,
  depth = MAX_DEPTH,
  maxStringLength = MAX_STRING_LENGTH,
): JsonValue | undefined {
  if (value === null) {
    return null;
  }

  if (value === undefined || typeof value === 'function') {
    return undefined;
  }

  if (typeof value === 'string') {
    return truncateString(value, maxStringLength);
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }

  if (depth <= 0) {
    return undefined;
  }

  if (Array.isArray(value)) {
    const items: JsonValue[] = [];

    for (const item of value.slice(0, MAX_ARRAY_ITEMS)) {
      const sanitized = sanitizeJsonValue(item, depth - 1, maxStringLength);
      if (sanitized !== undefined) {
        items.push(sanitized);
      }
    }

    return items;
  }

  if (typeof value === 'object') {
    const result: Record<string, JsonValue> = {};

    for (const [key, entry] of Object.entries(value).slice(
      0,
      MAX_OBJECT_KEYS,
    )) {
      const sanitized = sanitizeJsonValue(entry, depth - 1, maxStringLength);
      if (sanitized !== undefined) {
        result[key] = sanitized;
      }
    }

    return result;
  }

  return truncateString(String(value), maxStringLength);
}

function sanitizeOptionalString(value: unknown, maxLength = MAX_STRING_LENGTH) {
  if (typeof value !== 'string') {
    return undefined;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  return truncateString(trimmed, maxLength);
}

function sanitizeToolArguments(value: unknown) {
  if (typeof value !== 'string') {
    return '{}';
  }

  try {
    const parsed = JSON.parse(value);
    return JSON.stringify(
      sanitizeJsonValue(parsed, MAX_DEPTH, MAX_TOOL_STRING_LENGTH) ?? {},
    );
  } catch {
    return truncateString(value, MAX_TOOL_STRING_LENGTH);
  }
}

function sanitizeToolContent(value: unknown) {
  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(value);
        return JSON.stringify(
          sanitizeJsonValue(parsed, MAX_DEPTH, MAX_TOOL_STRING_LENGTH) ?? null,
        );
      } catch {
        return truncateString(value, MAX_TOOL_STRING_LENGTH);
      }
    }

    return truncateString(value, MAX_TOOL_STRING_LENGTH);
  }

  return JSON.stringify(
    sanitizeJsonValue(value, MAX_DEPTH, MAX_TOOL_STRING_LENGTH) ?? null,
  );
}

function sanitizeUserContent(content: unknown) {
  if (typeof content === 'string') {
    return truncateString(content);
  }

  if (!Array.isArray(content)) {
    return '';
  }

  const items: SanitizedUserContentItem[] = [];

  for (const item of content.slice(0, MAX_ARRAY_ITEMS)) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      continue;
    }

    const candidate = item as Record<string, unknown>;
    if (candidate.type === 'text' && typeof candidate.text === 'string') {
      items.push({
        type: 'text',
        text: truncateString(candidate.text),
      });
      continue;
    }

    if (candidate.type === 'binary' && typeof candidate.mimeType === 'string') {
      items.push({
        type: 'binary',
        mimeType: truncateString(candidate.mimeType, 120),
        ...(typeof candidate.filename === 'string'
          ? { filename: truncateString(candidate.filename, 240) }
          : {}),
        ...(typeof candidate.id === 'string'
          ? { id: truncateString(candidate.id, 120) }
          : {}),
        ...(typeof candidate.url === 'string'
          ? { url: truncateString(candidate.url, 500) }
          : {}),
      });
    }
  }

  return items;
}

function sanitizeToolCalls(value: unknown) {
  if (!Array.isArray(value)) {
    return undefined;
  }

  const toolCalls = value.slice(0, MAX_TOOL_CALLS).flatMap((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      return [];
    }

    const candidate = item as Record<string, unknown>;
    const functionCandidate =
      candidate.function &&
      typeof candidate.function === 'object' &&
      !Array.isArray(candidate.function)
        ? (candidate.function as Record<string, unknown>)
        : null;
    const id = sanitizeOptionalString(candidate.id, 120);
    const name = sanitizeOptionalString(functionCandidate?.name, 120);

    if (!id || !name) {
      return [];
    }

    return [
      {
        id,
        type: 'function' as const,
        function: {
          name,
          arguments: sanitizeToolArguments(functionCandidate?.arguments),
        },
      },
    ];
  });

  return toolCalls.length ? toolCalls : undefined;
}

function sanitizeMessage(message: unknown, index: number): Message | null {
  if (!message || typeof message !== 'object' || Array.isArray(message)) {
    return null;
  }

  const candidate = message as Record<string, unknown>;
  const role = candidate.role;
  const id =
    sanitizeOptionalString(candidate.id, 120) ?? `snapshot-message-${index}`;

  switch (role) {
    case 'assistant': {
      const content = sanitizeOptionalString(
        candidate.content,
        MAX_TOOL_STRING_LENGTH,
      );
      const toolCalls = sanitizeToolCalls(candidate.toolCalls);
      const name = sanitizeOptionalString(candidate.name, 120);

      if (!content && !toolCalls?.length) {
        return null;
      }

      return {
        id,
        role,
        ...(name ? { name } : {}),
        ...(content ? { content } : {}),
        ...(toolCalls ? { toolCalls } : {}),
      } as Message;
    }
    case 'user': {
      const content = sanitizeUserContent(candidate.content);
      const name = sanitizeOptionalString(candidate.name, 120);

      if (
        (typeof content === 'string' && !content) ||
        (Array.isArray(content) && !content.length)
      ) {
        return null;
      }

      return {
        id,
        role,
        ...(name ? { name } : {}),
        content,
      } as Message;
    }
    case 'tool': {
      const toolCallId = sanitizeOptionalString(candidate.toolCallId, 120);
      if (!toolCallId) {
        return null;
      }

      const error = sanitizeOptionalString(
        candidate.error,
        MAX_TOOL_STRING_LENGTH,
      );
      const toolName = sanitizeOptionalString(candidate.toolName, 120);

      return {
        id,
        role,
        toolCallId,
        content: sanitizeToolContent(candidate.content),
        ...(error ? { error } : {}),
        ...(toolName ? { toolName } : {}),
      } as Message;
    }
    case 'reasoning': {
      const content = sanitizeOptionalString(
        candidate.content,
        MAX_TOOL_STRING_LENGTH,
      );
      if (!content) {
        return null;
      }

      return {
        id,
        role,
        content,
      } as Message;
    }
    case 'activity': {
      const activityType = sanitizeOptionalString(candidate.activityType, 120);
      if (!activityType) {
        return null;
      }

      const content = sanitizeJsonValue(candidate.content);

      return {
        id,
        role,
        activityType,
        content:
          content && typeof content === 'object' && !Array.isArray(content)
            ? (content as Record<string, JsonValue>)
            : {},
      } as Message;
    }
    case 'system':
    case 'developer': {
      const content = sanitizeOptionalString(
        candidate.content,
        MAX_TOOL_STRING_LENGTH,
      );
      if (!content) {
        return null;
      }

      return {
        id,
        role,
        content,
      } as Message;
    }
    default:
      return null;
  }
}

function sanitizeSnapshotList(input: unknown) {
  return Array.isArray(input)
    ? input.flatMap((message, index) => {
        const sanitized = sanitizeMessage(message, index);
        return sanitized ? [sanitized] : [];
      })
    : [];
}

function fitSnapshotBudget(messages: Message[]) {
  let trimmed = messages.slice(-MAX_SNAPSHOT_MESSAGES);
  let json = JSON.stringify(trimmed);

  while (trimmed.length > 1 && byteLength(json) > MAX_SNAPSHOT_BYTES) {
    trimmed = trimmed.slice(1);
    json = JSON.stringify(trimmed);
  }

  if (byteLength(json) > MAX_SNAPSHOT_BYTES) {
    return {
      messages: [] as Message[],
      json: '[]',
      truncated: trimmed.length > 0,
    };
  }

  return {
    messages: trimmed,
    json,
    truncated: trimmed.length !== messages.length,
  };
}

export function normalizeSnapshotMessages(input: unknown) {
  return fitSnapshotBudget(sanitizeSnapshotList(input)).messages;
}

export function serializeSnapshotMessages(input: unknown) {
  return fitSnapshotBudget(sanitizeSnapshotList(input));
}

export function isSnapshotRequestTooLarge(body: string) {
  return byteLength(body) > MAX_SNAPSHOT_REQUEST_BYTES;
}
