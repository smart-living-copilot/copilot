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

import {
  GroupedToolCallsView,
  isFirstToolOnlyMessageInGroup,
  isToolOnlyAssistantMessage,
} from '@/components/copilot/chat-tool-calls/grouped-tool-calls-view';
import { WotInteractionSummaryCard } from '@/components/copilot/wot-summary/wot-interaction-summary-card';
import { cn } from '@/lib/utils';
import {
  looksLikeDeviceInteractionSummaryContent,
  parseDeviceInteractionSummaryContent,
} from '@/lib/wot-interactions';

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
    const interactions = parseDeviceInteractionSummaryContent(message.content);
    if (interactions.length > 0) {
      return <WotInteractionSummaryCard interactions={interactions} />;
    }
    if (looksLikeDeviceInteractionSummaryContent(message.content)) {
      return null;
    }
    if (isToolOnlyAssistantMessage(message)) {
      if (!isFirstToolOnlyMessageInGroup({ message, messages })) {
        return null;
      }

      return <GroupedToolCallsView message={message} messages={messages} />;
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
      >
        {({ interruptElement, isRunning, messageElements }) => {
          const showCursor =
            isRunning && displayMessages.at(-1)?.role !== 'reasoning';

          return (
            <div
              className="copilotKitMessages flex min-h-0 flex-1 flex-col"
              data-copilotkit
              data-testid="copilot-message-list"
            >
              <VirtualizedMessageElements messageElements={messageElements} />
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
