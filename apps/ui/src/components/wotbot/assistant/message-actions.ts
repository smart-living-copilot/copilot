import { WOT_SUMMARY_NAME } from '@/lib/thread-messages';

type AssistantMessageActionState = {
  message: {
    content: readonly {
      type: string;
      text?: string;
    }[];
    status?: {
      type: string;
    };
  };
};

type AssistantReloadActionState = AssistantMessageActionState & {
  thread: {
    capabilities: {
      reload: boolean;
    };
  };
};

type RetryMessage = {
  id?: string;
  role: string;
  content:
    | string
    | readonly {
        args?: unknown;
        type: string;
        text?: string;
        toolName?: string;
      }[];
};

export type RetryTarget = {
  sourceId: string | null;
  text: string;
};

const DEVICE_CHANGE_TYPES = new Set(['invoke_action', 'write_property']);

function retryUserMessageIndex(
  messages: readonly RetryMessage[],
  parentId: string | null,
): number {
  const parentIndex = messages.findIndex((message) => message.id === parentId);
  if (parentIndex < 0) {
    return -1;
  }

  for (let index = parentIndex; index >= 0; index -= 1) {
    if (messages[index]?.role === 'user') {
      return index;
    }
  }

  return -1;
}

/**
 * Whether the message already shows reasoning, which carries its own activity
 * animation.
 *
 * The empty running text part that precedes an answer and a streaming reasoning
 * part overlap in time, so without this check a reasoning turn renders two
 * "Thinking" animations at once. Reasoning wins because it can be expanded; a
 * turn with no reasoning still falls back to the plain indicator.
 */
export function hasVisibleReasoning(
  state: AssistantMessageActionState,
): boolean {
  return state.message.content.some(
    (part) => part.type === 'reasoning' && Boolean(part.text?.trim()),
  );
}

/** Only settled assistant responses with visible text and no tool calls get actions. */
export function hasAssistantResponseActions(
  state: AssistantMessageActionState,
): boolean {
  if (state.message.status?.type === 'running') {
    return false;
  }

  let hasVisibleText = false;
  for (const part of state.message.content) {
    if (part.type === 'tool-call') {
      return false;
    }
    if (part.type === 'text' && part.text?.trim()) {
      hasVisibleText = true;
    }
  }
  return hasVisibleText;
}

/** Reload is only available when the active runtime implements it. */
export function hasAssistantReloadAction(
  state: AssistantReloadActionState,
): boolean {
  return state.thread.capabilities.reload && hasAssistantResponseActions(state);
}

/** Find the user turn that owns the assistant response being regenerated. */
export function findRetryTarget(
  messages: readonly RetryMessage[],
  parentId: string | null,
): RetryTarget | null {
  const userIndex = retryUserMessageIndex(messages, parentId);
  if (userIndex < 0) {
    return null;
  }

  const message = messages[userIndex];
  if (!message) return null;
  const text =
    typeof message.content === 'string'
      ? message.content.trim()
      : message.content
          .filter(
            (part): part is { type: 'text'; text: string } =>
              part.type === 'text' && typeof part.text === 'string',
          )
          .map((part) => part.text)
          .join('\n')
          .trim();
  return text ? { sourceId: message.id ?? null, text } : null;
}

/** Counts successful physical changes anywhere in the turn being regenerated. */
export function countDeviceChangesForRetry(
  messages: readonly RetryMessage[],
  parentId: string | null,
): number {
  const userIndex = retryUserMessageIndex(messages, parentId);
  if (userIndex < 0) {
    return 0;
  }

  let count = 0;
  for (let index = userIndex + 1; index < messages.length; index += 1) {
    const message = messages[index];
    if (!message || message.role === 'user') {
      break;
    }
    if (typeof message.content === 'string') {
      continue;
    }

    for (const part of message.content) {
      if (part.type !== 'tool-call' || part.toolName !== WOT_SUMMARY_NAME) {
        continue;
      }
      const args =
        part.args && typeof part.args === 'object' && !Array.isArray(part.args)
          ? (part.args as { interactions?: unknown }).interactions
          : undefined;
      if (!Array.isArray(args)) {
        continue;
      }
      count += args.filter((interaction) => {
        if (
          !interaction ||
          typeof interaction !== 'object' ||
          Array.isArray(interaction)
        ) {
          return false;
        }
        const candidate = interaction as { ok?: unknown; type?: unknown };
        return (
          candidate.ok !== false &&
          typeof candidate.type === 'string' &&
          DEVICE_CHANGE_TYPES.has(candidate.type)
        );
      }).length;
    }
  }

  return count;
}
