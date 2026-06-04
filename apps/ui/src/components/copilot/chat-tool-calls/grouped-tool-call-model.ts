import {
  type AssistantMessage,
  type Message,
  type ToolCall,
  type ToolMessage,
} from '@ag-ui/core';

import {
  type CatchAllToolCallRenderProps,
  type ToolCallStatus,
} from '../chat-tool-call-model';

export type ToolStatusCounts = Record<ToolCallStatus, number>;

export function createToolStatusCounts(): ToolStatusCounts {
  return {
    complete: 0,
    executing: 0,
    inProgress: 0,
  };
}

export function isToolOnlyAssistantMessage(
  message: Message,
): message is AssistantMessage {
  return (
    message.role === 'assistant' &&
    (message.toolCalls?.length ?? 0) > 0 &&
    !(message.content ?? '').trim()
  );
}

export function isFirstToolOnlyMessageInGroup({
  message,
  messages,
}: {
  message: AssistantMessage;
  messages: Message[];
}) {
  if (!isToolOnlyAssistantMessage(message)) {
    return true;
  }

  const messageIndex = messages.findIndex(
    (candidate) => candidate.id === message.id,
  );
  if (messageIndex <= 0) {
    return true;
  }

  for (let index = messageIndex - 1; index >= 0; index -= 1) {
    const previous = messages[index];
    if (!previous || previous.role === 'tool') {
      continue;
    }

    return !isToolOnlyAssistantMessage(previous);
  }

  return true;
}

export function getGroupedToolCalls({
  message,
  messages,
}: {
  message: AssistantMessage;
  messages: Message[];
}) {
  if (
    (message.toolCalls?.length ?? 0) === 0 ||
    (message.content ?? '').trim()
  ) {
    return message.toolCalls ?? [];
  }

  const groupedToolCalls: ToolCall[] = [];
  const messageIndex = messages.findIndex(
    (candidate) => candidate.id === message.id,
  );
  if (messageIndex < 0) {
    return message.toolCalls ?? [];
  }

  for (let index = messageIndex; index < messages.length; index += 1) {
    const current = messages[index];
    if (!current) {
      continue;
    }
    if (current.role === 'tool') {
      continue;
    }
    if (!isToolOnlyAssistantMessage(current)) {
      break;
    }

    groupedToolCalls.push(...(current.toolCalls ?? []));
  }

  return groupedToolCalls;
}

export function getToolMessageForCall({
  messages,
  toolCall,
}: {
  messages: Message[];
  toolCall: ToolCall;
}) {
  return messages.find(
    (candidate): candidate is ToolMessage =>
      candidate.role === 'tool' && candidate.toolCallId === toolCall.id,
  );
}

function parseToolArgs(rawArgs: string) {
  try {
    const parsed = JSON.parse(rawArgs);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed
      : {};
  } catch {
    return {};
  }
}

function getToolStatus({
  executingToolCallIds,
  toolCall,
  toolMessage,
}: {
  executingToolCallIds: ReadonlySet<string>;
  toolCall: ToolCall;
  toolMessage?: ToolMessage;
}): ToolCallStatus {
  if (toolMessage) {
    return 'complete';
  }

  return executingToolCallIds.has(toolCall.id) ? 'executing' : 'inProgress';
}

export function buildToolCallProps({
  executingToolCallIds,
  toolCall,
  toolMessage,
}: {
  executingToolCallIds: ReadonlySet<string>;
  toolCall: ToolCall;
  toolMessage?: ToolMessage;
}): CatchAllToolCallRenderProps {
  return {
    args: parseToolArgs(toolCall.function.arguments),
    name: toolCall.function.name,
    result: toolMessage?.content,
    status: getToolStatus({ executingToolCallIds, toolCall, toolMessage }),
  };
}

export function formatToolCount(count: number) {
  return `${count} tool${count === 1 ? '' : 's'} called`;
}

export function formatToolStatusSummary({
  completeCount,
  count,
  executingCount,
  inProgressCount,
}: {
  completeCount: number;
  count: number;
  executingCount: number;
  inProgressCount: number;
}) {
  if (completeCount === count) {
    return 'Finished';
  }

  const parts = [];
  if (executingCount) {
    parts.push(`${executingCount} running`);
  }
  if (inProgressCount) {
    parts.push(`${inProgressCount} preparing`);
  }
  if (completeCount) {
    parts.push(`${completeCount} complete`);
  }

  return parts.join(' • ') || 'Working';
}
