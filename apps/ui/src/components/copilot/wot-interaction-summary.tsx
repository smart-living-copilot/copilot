'use client';

import { memo, useMemo, type ComponentProps } from 'react';
import {
  CopilotChatAssistantMessage,
  CopilotChatMessageView,
} from '@copilotkit/react-core/v2';

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

    return (
      <CopilotChatAssistantMessage
        {...props}
        className={className}
        isRunning={isRunning}
        message={message}
        messages={messages}
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
      />
    </div>
  );
}

export const MessageViewWithWotSummary = Object.assign(
  MessageViewWithWotSummaryImpl,
  {
    Cursor: CopilotChatMessageView.Cursor,
  },
);
