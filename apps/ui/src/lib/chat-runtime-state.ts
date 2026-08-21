import type { LangChainMessage } from '@/lib/thread-messages';

export type WotbotState = {
  messages: LangChainMessage[];
  reasoning_effort?: string;
};

export type TextSubmission = {
  input: Partial<WotbotState>;
  optimisticValues: WotbotState;
};

/**
 * Builds one text run without discarding turns streamed since page load.
 *
 * The custom LangGraph transport resets to `initialValues` at the start of
 * every submission unless `optimisticValues` is supplied. Carrying the latest
 * values forward also makes the new user turn appear immediately, before the
 * router or model emits its first server event.
 */
export function buildTextSubmission({
  currentValues,
  initialValues,
  messageId,
  reasoningEffort,
  replaceFromId,
  text,
}: {
  currentValues: Partial<WotbotState>;
  initialValues: WotbotState;
  messageId: string;
  reasoningEffort?: string;
  replaceFromId?: string | null;
  text: string;
}): TextSubmission {
  const currentMessages = Array.isArray(currentValues.messages)
    ? currentValues.messages
    : initialValues.messages;
  const replaceIndex = replaceFromId
    ? currentMessages.findIndex((message) => message.id === replaceFromId)
    : -1;
  const baseMessages =
    replaceIndex >= 0
      ? currentMessages.slice(0, replaceIndex)
      : currentMessages;
  const humanMessage: LangChainMessage = {
    type: 'human',
    content: text,
    id: messageId,
  };
  const effortState = reasoningEffort
    ? { reasoning_effort: reasoningEffort }
    : {};

  return {
    input: {
      messages: [humanMessage],
      ...effortState,
    },
    optimisticValues: {
      ...initialValues,
      ...currentValues,
      messages: [...baseMessages, humanMessage],
      ...effortState,
    },
  };
}
