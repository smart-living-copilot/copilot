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
        type: string;
        text?: string;
      }[];
};

export type RetryTarget = {
  sourceId: string | null;
  text: string;
};

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
  const parentIndex = messages.findIndex((message) => message.id === parentId);
  if (parentIndex < 0) {
    return null;
  }

  for (let index = parentIndex; index >= 0; index -= 1) {
    const message = messages[index];
    if (message?.role !== 'user') {
      continue;
    }

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

  return null;
}
