'use client';

import { CopilotKit } from '@copilotkit/react-core/v2';
import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';

import { createChat } from '@/components/copilot/chat-route/chat-api';
import { ChatIndexPage } from '@/components/copilot/chat-route/chat-index-page';
import { EmbedChatExperience } from '@/components/copilot/chat-route/embed-chat-experience';
import { FullChatExperience } from '@/components/copilot/chat-route/full-chat-experience';
import { chatToolCallRenderers } from './chat-tool-call-renderer';
import { createEmbedEphemeralChatId } from '@/lib/embed-chat';

export { ChatIndexPage };

export type ChatRouteMode = 'full' | 'embed';

function toQuerySuffix(queryString: string): string {
  return queryString ? `?${queryString}` : '';
}

export function ChatRoutePage({
  chatId,
  mode,
  embedQueryString = '',
  showEmbedExamplePrompts = true,
}: {
  chatId: string;
  mode: ChatRouteMode;
  embedQueryString?: string;
  showEmbedExamplePrompts?: boolean;
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
      agent="copilot"
      threadId={chatId}
      enableInspector={enableInspector}
      renderToolCalls={chatToolCallRenderers}
    >
      {mode === 'embed' ? (
        <EmbedChatExperience
          chatId={chatId}
          showExamplePrompts={showEmbedExamplePrompts}
        />
      ) : (
        <FullChatExperience chatId={chatId} handleNewChat={handleNewChat} />
      )}
    </CopilotKit>
  );
}

export function EmbedChatPage({
  embedQueryString = '',
  showEmbedExamplePrompts = true,
}: {
  embedQueryString?: string;
  showEmbedExamplePrompts?: boolean;
}) {
  const [chatId] = useState(() => createEmbedEphemeralChatId());

  return (
    <ChatRoutePage
      chatId={chatId}
      mode="embed"
      embedQueryString={embedQueryString}
      showEmbedExamplePrompts={showEmbedExamplePrompts}
    />
  );
}
