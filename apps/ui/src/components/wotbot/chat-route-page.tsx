'use client';

import { CopilotKit } from '@copilotkit/react-core/v2';
import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';

import { createChat } from '@/components/wotbot/chat-route/chat-api';
import { ChatIndexPage } from '@/components/wotbot/chat-route/chat-index-page';
import { EmbedChatExperience } from '@/components/wotbot/chat-route/embed-chat-experience';
import { FullChatExperience } from '@/components/wotbot/chat-route/full-chat-experience';
import { chatToolCallRenderers } from './chat-tool-call-renderer';
import {
  createEmbedEphemeralChatId,
  type EmbedChatPrefill,
} from '@/lib/embed-chat';
import type { Theme } from '@/components/theme-provider';

export { ChatIndexPage };

export type ChatRouteMode = 'full' | 'embed';

function toQuerySuffix(queryString: string): string {
  return queryString ? `?${queryString}` : '';
}

export function ChatRoutePage({
  allowedPrefillOrigins = [],
  chatId,
  mode,
  embedQueryString = '',
  embedTheme = null,
  initialEmbedPrefill = null,
}: {
  allowedPrefillOrigins?: string[];
  chatId: string;
  mode: ChatRouteMode;
  embedQueryString?: string;
  embedTheme?: Theme | null;
  initialEmbedPrefill?: EmbedChatPrefill | null;
}) {
  const enableInspector =
    process.env.NEXT_PUBLIC_ENABLE_COPILOT_INSPECTOR === 'true';
  const router = useRouter();
  const querySuffix = toQuerySuffix(embedQueryString);

  const handleNewChat = useCallback(async () => {
    try {
      const chat = await createChat();
      const basePath = mode === 'embed' ? '/embed/chat' : '/chat';
      const suffix = mode === 'embed' ? querySuffix : '';
      router.push(`${basePath}/${chat.id}${suffix}`);
      return chat;
    } catch (error) {
      console.error('Failed to create chat', error);
      return null;
    }
  }, [mode, querySuffix, router]);

  return (
    <CopilotKit
      key={chatId}
      runtimeUrl="/api/copilotkit"
      agent="wotbot"
      threadId={chatId}
      enableInspector={enableInspector}
      renderToolCalls={chatToolCallRenderers}
    >
      {mode === 'embed' ? (
        <EmbedChatExperience
          allowedPrefillOrigins={allowedPrefillOrigins}
          chatId={chatId}
          embedTheme={embedTheme}
          initialPrefill={initialEmbedPrefill}
        />
      ) : (
        <FullChatExperience chatId={chatId} handleNewChat={handleNewChat} />
      )}
    </CopilotKit>
  );
}

export function EmbedChatPage({
  allowedPrefillOrigins = [],
  embedQueryString = '',
  embedTheme = null,
  initialPrefill = null,
}: {
  allowedPrefillOrigins?: string[];
  embedQueryString?: string;
  embedTheme?: Theme | null;
  initialPrefill?: EmbedChatPrefill | null;
}) {
  const [chatId] = useState(() => createEmbedEphemeralChatId());

  return (
    <ChatRoutePage
      allowedPrefillOrigins={allowedPrefillOrigins}
      chatId={chatId}
      mode="embed"
      embedQueryString={embedQueryString}
      embedTheme={embedTheme}
      initialEmbedPrefill={initialPrefill}
    />
  );
}
