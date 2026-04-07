import type { Message } from '@ag-ui/core';

const WOT_DIRECT_TOOL_NAMES = new Set([
  'wot_invoke_action',
  'wot_read_property',
  'wot_write_property',
  'wot_observe_property',
  'wot_subscribe_event',
]);

type ToolCallEntry = {
  args: Record<string, unknown>;
  name: string;
};

export type WotInteraction = {
  affordanceName: string;
  input?: unknown;
  ok: boolean;
  thingId: string;
  type: string;
  uriVariables?: Record<string, unknown>;
  value?: unknown;
};

function parseJsonRecord(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }

  return value as Record<string, unknown>;
}

function parseToolArguments(value: unknown) {
  if (typeof value === 'string') {
    try {
      return parseJsonRecord(JSON.parse(value));
    } catch {
      return {};
    }
  }

  return parseJsonRecord(value);
}

function parseOptionalRecord(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined;
  }

  const record = value as Record<string, unknown>;
  return Object.keys(record).length ? record : undefined;
}

function isErrorResult(value: unknown) {
  if (typeof value === 'string') {
    return /^error\b/i.test(value.trim());
  }

  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }

  const error = (value as { error?: unknown }).error;
  return typeof error === 'string' && error.trim().length > 0;
}

function normalizeWotInteraction(value: unknown): WotInteraction | null {
  const candidate = parseJsonRecord(value);
  const type = typeof candidate.type === 'string' ? candidate.type : '';
  const uriVariables = parseOptionalRecord(
    candidate.uri_variables ?? candidate.uriVariables,
  );
  const thingId =
    typeof candidate.thing_id === 'string'
      ? candidate.thing_id
      : typeof candidate.thingId === 'string'
        ? candidate.thingId
        : '';

  if (!type || !thingId) {
    return null;
  }

  const affordanceName =
    typeof candidate.name === 'string'
      ? candidate.name
      : typeof candidate.affordanceName === 'string'
        ? candidate.affordanceName
        : '';

  return {
    affordanceName,
    ok: candidate.ok !== false,
    thingId,
    type,
    ...(candidate.input !== undefined ? { input: candidate.input } : {}),
    ...(candidate.value !== undefined ? { value: candidate.value } : {}),
    ...(uriVariables ? { uriVariables } : {}),
  };
}

function parseDirectToolCall(
  name: string,
  args: Record<string, unknown>,
  result: unknown,
): WotInteraction | null {
  if (!WOT_DIRECT_TOOL_NAMES.has(name)) {
    return null;
  }

  const affordanceName =
    (args.action_name as string) ||
    (args.property_name as string) ||
    (args.event_name as string) ||
    '';
  const uriVariables = parseOptionalRecord(args.uri_variables);
  const thingId = typeof args.thing_id === 'string' ? args.thing_id : '';

  if (!thingId) {
    return null;
  }

  return {
    affordanceName,
    ok: !isErrorResult(result),
    thingId,
    type: name.replace('wot_', ''),
    ...(args.input !== undefined ? { input: args.input } : {}),
    ...(args.value !== undefined ? { value: args.value } : {}),
    ...(uriVariables ? { uriVariables } : {}),
  };
}

export function parseWotInteractionList(value: unknown): WotInteraction[] {
  let parsed = value;

  if (typeof parsed === 'string') {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      return [];
    }
  }

  const rawList = Array.isArray(parsed)
    ? parsed
    : parseJsonRecord(parsed).wot_calls;

  if (!Array.isArray(rawList)) {
    return [];
  }

  return rawList.flatMap((entry) => {
    const interaction = normalizeWotInteraction(entry);
    return interaction ? [interaction] : [];
  });
}

export function extractWotInteractions(messages: Message[]) {
  const toolCallsById = new Map<string, ToolCallEntry>();

  for (const message of messages) {
    if (message.role !== 'assistant' || !message.toolCalls) {
      continue;
    }

    for (const toolCall of message.toolCalls) {
      toolCallsById.set(toolCall.id, {
        args: parseToolArguments(toolCall.function?.arguments),
        name: toolCall.function?.name ?? '',
      });
    }
  }

  const interactions: WotInteraction[] = [];

  for (const message of messages) {
    if (message.role !== 'tool' || !message.toolCallId) {
      continue;
    }

    const toolCall = toolCallsById.get(message.toolCallId);
    if (!toolCall) {
      continue;
    }

    const directInteraction = parseDirectToolCall(
      toolCall.name,
      toolCall.args,
      message.content,
    );
    if (directInteraction) {
      interactions.push(directInteraction);
      continue;
    }

    if (toolCall.name === 'run_code') {
      interactions.push(...parseWotInteractionList(message.content));
    }
  }

  return interactions;
}

export function getLastTurnWotInteractions(messages: Message[]) {
  let lastUserIndex = -1;

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === 'user') {
      lastUserIndex = index;
      break;
    }
  }

  if (lastUserIndex < 0) {
    return [];
  }

  return extractWotInteractions(messages.slice(lastUserIndex));
}
