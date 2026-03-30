'use client';

import { type MessagesProps, useChatContext } from '@copilotkit/react-ui';
import { useLazyToolRenderer } from '@copilotkit/react-core';
import type { Message } from '@copilotkit/shared';
import { type MutableRefObject, useEffect, useMemo, useRef } from 'react';
import { serializeSnapshotMessages } from '@/lib/chat-snapshots';

function makeInitialMessages(
  initial: string | string[] | undefined,
): Message[] {
  if (!initial) {
    return [];
  }

  if (Array.isArray(initial)) {
    return initial.map((message) => ({
      id: message,
      role: 'assistant',
      content: message,
    }));
  }

  return [
    {
      id: initial,
      role: 'assistant',
      content: initial,
    },
  ];
}

function dedupeMessages(messages: Message[]): Message[] {
  const latestById = new Map<string, Message>();
  for (const message of messages) {
    latestById.set(message.id, message);
  }

  const deduped: Message[] = [];
  const seen = new Set<string>();
  for (const message of messages) {
    const latest = latestById.get(message.id);
    if (!latest || seen.has(latest.id)) {
      continue;
    }
    seen.add(latest.id);
    deduped.push(latest);
  }

  return deduped;
}

function persistMessages(
  chatId: string,
  messages: Message[],
  payload: string,
  lastSavedPayloadRef: MutableRefObject<string | null>,
) {
  void fetch(`/api/chats/${chatId}/messages`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      messages,
    }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Failed to persist chat snapshot (${response.status})`);
      }
      lastSavedPayloadRef.current = payload;
    })
    .catch((error) => {
      console.error('Failed to persist chat snapshot', error);
    });
}

function useScrollToBottom(messages: Message[]) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);
  const isProgrammaticScrollRef = useRef(false);
  const isUserScrollUpRef = useRef(false);

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) {
      return;
    }

    const handleScroll = () => {
      if (isProgrammaticScrollRef.current) {
        isProgrammaticScrollRef.current = false;
        return;
      }

      const { scrollTop, scrollHeight, clientHeight } = container;
      isUserScrollUpRef.current = scrollTop + clientHeight < scrollHeight;
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container || isUserScrollUpRef.current) {
      return;
    }

    isProgrammaticScrollRef.current = true;
    container.scrollTop = container.scrollHeight;
  }, [messages]);

  return {
    messagesContainerRef,
    messagesEndRef,
  };
}

type ChatMessagesProps = MessagesProps & {
  chatId: string;
  historyLoaded: boolean;
  persistedMessages: Message[];
};

export function ChatMessages({
  AssistantMessage,
  ErrorMessage,
  ImageRenderer,
  RenderMessage,
  UserMessage,
  chatError,
  chatId,
  children,
  historyLoaded,
  inProgress,
  markdownTagRenderers,
  messageFeedback,
  messages,
  onCopy,
  onRegenerate,
  onThumbsDown,
  onThumbsUp,
  persistedMessages,
}: ChatMessagesProps) {
  const { icons, labels } = useChatContext();
  const renderToolCall = useLazyToolRenderer();
  const persistTimeoutRef = useRef<number | null>(null);
  const lastSavedPayloadRef = useRef<string | null>(null);

  const liveMessages = useMemo(() => dedupeMessages(messages), [messages]);
  const snapshotMessages = useMemo(
    () => dedupeMessages(persistedMessages),
    [persistedMessages],
  );
  const initialMessages = useMemo(
    () => makeInitialMessages(labels.initial),
    [labels.initial],
  );

  useEffect(() => {
    if (!historyLoaded) {
      return;
    }

    lastSavedPayloadRef.current =
      serializeSnapshotMessages(snapshotMessages).json;
  }, [historyLoaded, snapshotMessages, chatId]);

  const renderableMessages = useMemo(() => {
    const baseMessages = dedupeMessages([
      ...initialMessages,
      ...snapshotMessages,
      ...liveMessages,
    ]);

    return baseMessages.map((message) => {
      if (
        message.role !== 'assistant' ||
        message.generativeUI ||
        !message.toolCalls?.length
      ) {
        return message;
      }

      const toolCall = message.toolCalls[0];
      if (!toolCall) {
        return message;
      }

      const toolMessage = baseMessages.find(
        (candidate) =>
          candidate.role === 'tool' && candidate.toolCallId === toolCall.id,
      );

      if (!toolMessage) {
        return message;
      }

      return {
        ...message,
        generativeUI: renderToolCall(message, baseMessages) ?? undefined,
        generativeUIPosition: 'before' as const,
      };
    });
  }, [initialMessages, liveMessages, renderToolCall, snapshotMessages]);
  const liveMessageIds = useMemo(
    () => new Set(liveMessages.map((message) => message.id)),
    [liveMessages],
  );

  const persistableMessages = useMemo(
    () => dedupeMessages([...snapshotMessages, ...liveMessages]),
    [liveMessages, snapshotMessages],
  );
  const serializedPersistableMessages = useMemo(
    () => serializeSnapshotMessages(persistableMessages),
    [persistableMessages],
  );

  useEffect(() => {
    if (!historyLoaded) {
      return;
    }

    const { json: payload, messages: normalizedMessages } =
      serializedPersistableMessages;
    if (payload === lastSavedPayloadRef.current) {
      return;
    }

    if (persistTimeoutRef.current) {
      window.clearTimeout(persistTimeoutRef.current);
    }

    persistTimeoutRef.current = window.setTimeout(() => {
      persistMessages(chatId, normalizedMessages, payload, lastSavedPayloadRef);
    }, 400);

    return () => {
      if (persistTimeoutRef.current) {
        window.clearTimeout(persistTimeoutRef.current);
      }
    };
  }, [chatId, historyLoaded, serializedPersistableMessages]);

  const { messagesContainerRef, messagesEndRef } =
    useScrollToBottom(renderableMessages);

  return (
    <div className="copilotKitMessages" ref={messagesContainerRef}>
      <div className="copilotKitMessagesContainer">
        {renderableMessages.map((message, index) => {
          const isCurrentMessage = index === renderableMessages.length - 1;
          const allowRegenerate = liveMessageIds.has(message.id)
            ? onRegenerate
            : undefined;
          return (
            <RenderMessage
              key={message.id}
              AssistantMessage={AssistantMessage}
              ImageRenderer={ImageRenderer}
              UserMessage={UserMessage}
              index={index}
              inProgress={inProgress}
              isCurrentMessage={isCurrentMessage}
              markdownTagRenderers={markdownTagRenderers}
              message={message}
              messageFeedback={messageFeedback}
              messages={renderableMessages}
              onCopy={onCopy}
              onRegenerate={allowRegenerate}
              onThumbsDown={onThumbsDown}
              onThumbsUp={onThumbsUp}
            />
          );
        })}

        {renderableMessages[renderableMessages.length - 1]?.role === 'user' &&
        inProgress ? (
          <span>{icons.activityIcon}</span>
        ) : null}

        {chatError && ErrorMessage ? (
          <ErrorMessage error={chatError} isCurrentMessage />
        ) : null}
      </div>

      <footer className="copilotKitMessagesFooter" ref={messagesEndRef}>
        {children}
      </footer>
    </div>
  );
}
