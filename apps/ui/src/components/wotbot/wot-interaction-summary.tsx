'use client';

import {
  memo,
  useCallback,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type ReactElement,
} from 'react';
import {
  CopilotChatAssistantMessage,
  CopilotChatMessageView,
} from '@copilotkit/react-core/v2';
import { Virtualizer } from 'virtua';

import { GroupedToolCallsView } from '@/components/wotbot/chat-tool-calls/grouped-tool-calls-view';
import {
  isFirstToolOnlyMessageInGroup,
  isToolOnlyAssistantMessage,
} from '@/components/wotbot/chat-tool-calls/grouped-tool-call-model';
import { UserMessageWithEdit } from '@/components/wotbot/chat-route/user-message-with-edit';
import { WotInteractionSummaryCard } from '@/components/wotbot/wot-summary/wot-interaction-summary-card';
import { cn } from '@/lib/utils';
import {
  looksLikeDeviceInteractionSummaryContent,
  parseDeviceInteractionSummaryContent,
} from '@/lib/wot-interactions';

type ChatMessage = NonNullable<
  ComponentProps<typeof CopilotChatMessageView>['messages']
>[number];

function isIntentPayloadMessage(message: { content?: unknown }) {
  const content = message.content;
  const normalized =
    typeof content === 'string'
      ? content.trim()
      : Array.isArray(content) &&
          content.length === 1 &&
          typeof content[0] === 'string'
        ? content[0].trim()
        : null;

  if (!normalized) {
    return false;
  }

  try {
    const parsed = JSON.parse(normalized) as unknown;
    return (
      !!parsed &&
      typeof parsed === 'object' &&
      !Array.isArray(parsed) &&
      Object.keys(parsed).length === 1 &&
      (parsed as Record<string, unknown>).intent !== undefined &&
      ['analysis', 'chat', 'control'].includes(
        String((parsed as Record<string, unknown>).intent),
      )
    );
  } catch {
    return false;
  }
}

function getElementMessage({
  element,
  messages,
}: {
  element: ReactElement;
  messages: ChatMessage[];
}) {
  const key = element.key == null ? null : String(element.key);
  if (!key) {
    return null;
  }

  return messages.find((message) => message.id === key) ?? null;
}

function groupToolCallMessageElements({
  messageElements,
  messages,
}: {
  messageElements: ReactElement[];
  messages: ChatMessage[];
}) {
  return messageElements.flatMap((element) => {
    const message = getElementMessage({ element, messages });
    if (!message || !isToolOnlyAssistantMessage(message)) {
      return [element];
    }

    if (!isFirstToolOnlyMessageInGroup({ message, messages })) {
      return [];
    }

    return [
      <GroupedToolCallsView
        key={`tool-call-group-${message.id}`}
        message={message}
        messages={messages}
      />,
    ];
  });
}

function findScrollableAncestor(element: HTMLElement) {
  let parent = element.parentElement;

  while (parent && parent !== document.body) {
    const { overflowY } = window.getComputedStyle(parent);
    if (overflowY === 'auto' || overflowY === 'scroll') {
      return parent;
    }
    parent = parent.parentElement;
  }

  return null;
}

function VirtualizedMessageElements({
  messageElements,
}: {
  messageElements: ReactElement[];
}) {
  const scrollRef = useRef<HTMLElement | null>(null);
  const [hasScrollParent, setHasScrollParent] = useState(false);

  const setContainerRef = useCallback((element: HTMLDivElement | null) => {
    const scrollParent = element ? findScrollableAncestor(element) : null;
    scrollRef.current = scrollParent;
    setHasScrollParent(Boolean(scrollParent));
  }, []);

  return (
    <div ref={setContainerRef} className="min-h-0">
      {hasScrollParent ? (
        <Virtualizer
          data={messageElements}
          itemSize={160}
          keepMounted={
            messageElements.length > 0 ? [messageElements.length - 1] : []
          }
          scrollRef={scrollRef}
        >
          {(element: ReactElement) => element}
        </Virtualizer>
      ) : (
        messageElements
      )}
    </div>
  );
}

const AssistantMessageWithWotSummaryImpl = memo(
  function AssistantMessageWithWotSummary({
    className,
    isRunning = false,
    message,
    messages = [],
    ...props
  }: ComponentProps<typeof CopilotChatAssistantMessage>) {
    const explicitInteractions = useMemo(
      () => parseDeviceInteractionSummaryContent(message.content),
      [message.content],
    );

    if (explicitInteractions.length > 0) {
      return <WotInteractionSummaryCard interactions={explicitInteractions} />;
    }
    if (looksLikeDeviceInteractionSummaryContent(message.content)) {
      return null;
    }
    if (isToolOnlyAssistantMessage(message)) {
      return null;
    }

    return (
      <CopilotChatAssistantMessage
        {...props}
        className={className}
        isRunning={isRunning}
        message={message}
        messages={messages}
        toolCallsView={GroupedToolCallsView}
      />
    );
  },
);

const AssistantMessageWithWotSummary = Object.assign(
  AssistantMessageWithWotSummaryImpl,
  CopilotChatAssistantMessage,
);

function MessageViewWithWotSummaryImpl({
  className,
  isRunning = false,
  messages = [],
  ...props
}: ComponentProps<typeof CopilotChatMessageView>) {
  const displayMessages = useMemo(
    () => messages.filter((message) => !isIntentPayloadMessage(message)),
    [messages],
  );

  return (
    <div className={cn('flex flex-1 flex-col gap-3 pt-2', className)}>
      <CopilotChatMessageView
        {...props}
        assistantMessage={AssistantMessageWithWotSummary}
        isRunning={isRunning}
        messages={displayMessages}
        userMessage={UserMessageWithEdit}
      >
        {({ interruptElement, isRunning, messageElements }) => {
          const groupedMessageElements = groupToolCallMessageElements({
            messageElements,
            messages: displayMessages,
          });
          const showCursor =
            isRunning && displayMessages.at(-1)?.role !== 'reasoning';

          return (
            <div
              className="copilotKitMessages flex min-h-0 flex-1 flex-col"
              data-copilotkit
              data-testid="wotbot-message-list"
            >
              <VirtualizedMessageElements
                messageElements={groupedMessageElements}
              />
              {interruptElement}
              {showCursor ? (
                <div className="mt-2">
                  <CopilotChatMessageView.Cursor />
                </div>
              ) : null}
            </div>
          );
        }}
      </CopilotChatMessageView>
    </div>
  );
}

export const MessageViewWithWotSummary = Object.assign(
  MessageViewWithWotSummaryImpl,
  {
    Cursor: CopilotChatMessageView.Cursor,
  },
);
