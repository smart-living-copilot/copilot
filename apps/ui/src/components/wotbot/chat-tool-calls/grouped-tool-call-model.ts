import {
  type CatchAllToolCallRenderProps,
  type ToolCallStatus,
} from '../chat-tool-call-model';
import type { LangChainMessage } from '@/lib/thread-messages';

type ToolCall = NonNullable<LangChainMessage['tool_calls']>[number] & {
  id: string;
  name: string;
};
type AssistantMessage = LangChainMessage & {
  type: 'ai' | 'assistant' | 'AIMessageChunk';
  tool_calls: ToolCall[];
};
type ToolMessage = LangChainMessage & {
  type: 'tool';
  tool_call_id: string;
};

export type ToolStatusCounts = Record<ToolCallStatus, number>;

export function createToolStatusCounts(): ToolStatusCounts {
  return {
    complete: 0,
    executing: 0,
    inProgress: 0,
  };
}

export function isToolOnlyAssistantMessage(
  message: LangChainMessage,
): message is AssistantMessage {
  return (
    (message.type === 'ai' ||
      message.type === 'assistant' ||
      message.type === 'AIMessageChunk') &&
    (message.tool_calls?.length ?? 0) > 0 &&
    message.tool_calls?.every(
      (call) => typeof call.id === 'string' && typeof call.name === 'string',
    ) === true &&
    (typeof message.content !== 'string' || !message.content.trim())
  );
}

export function isFirstToolOnlyMessageInGroup({
  message,
  messages,
}: {
  message: AssistantMessage;
  messages: LangChainMessage[];
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
    if (!previous || previous.type === 'tool') {
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
  messages: LangChainMessage[];
}) {
  if (
    (message.tool_calls?.length ?? 0) === 0 ||
    (typeof message.content === 'string' && message.content.trim())
  ) {
    return message.tool_calls ?? [];
  }

  const groupedToolCalls: ToolCall[] = [];
  const messageIndex = messages.findIndex(
    (candidate) => candidate.id === message.id,
  );
  if (messageIndex < 0) {
    return message.tool_calls ?? [];
  }

  for (let index = messageIndex; index < messages.length; index += 1) {
    const current = messages[index];
    if (!current) {
      continue;
    }
    if (current.type === 'tool') {
      continue;
    }
    if (!isToolOnlyAssistantMessage(current)) {
      break;
    }

    groupedToolCalls.push(...(current.tool_calls ?? []));
  }

  return groupedToolCalls;
}

export function getToolMessageForCall({
  messages,
  toolCall,
}: {
  messages: LangChainMessage[];
  toolCall: ToolCall;
}) {
  return messages.find(
    (candidate): candidate is ToolMessage =>
      candidate.type === 'tool' && candidate.tool_call_id === toolCall.id,
  );
}

function parseToolArgs(rawArgs: unknown) {
  if (rawArgs && typeof rawArgs === 'object' && !Array.isArray(rawArgs)) {
    return rawArgs as Record<string, unknown>;
  }
  if (typeof rawArgs !== 'string') {
    return {};
  }
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
    args: parseToolArgs(toolCall.args),
    name: toolCall.name,
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
