'use client';

import { CopilotKit } from '@copilotkit/react-core';
import { CopilotChat, type MessagesProps } from '@copilotkit/react-ui';
import type { Message } from '@copilotkit/shared';
import { MessageSquarePlus } from 'lucide-react';
import { use, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AppSidebar } from '@/components/chat-sidebar';
import { ChatAssistantMessage } from '@/components/copilot/chat-assistant-message';
import { ChatMessages } from '@/components/copilot/chat-messages';
import { ChatToolCallRenderer } from '@/components/copilot/chat-tool-call-renderer';
import { SiteHeader } from '@/components/site-header';
import { Button } from '@/components/ui/button';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';

export default function ChatPage({
  params,
}: {
  params: Promise<{ chatId: string }>;
}) {
  const { chatId } = use(params);
  const router = useRouter();
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [persistedMessages, setPersistedMessages] = useState<Message[]>([]);
  const [sidebarRefreshToken, setSidebarRefreshToken] = useState(0);

  const breadcrumbs = useMemo(() => [{ label: 'Chat', href: '/chat' }], []);

  useEffect(() => {
    const abortController = new AbortController();

    setHistoryLoaded(false);
    setPersistedMessages([]);

    void fetch(`/api/chats/${chatId}/messages`, {
      signal: abortController.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error('Failed to load chat messages');
        }

        const payload = (await response.json()) as { messages?: Message[] };
        setPersistedMessages(
          Array.isArray(payload.messages) ? payload.messages : [],
        );
        setHistoryLoaded(true);
      })
      .catch((error) => {
        if (abortController.signal.aborted) {
          return;
        }

        console.error('Failed to load chat messages', error);
        setHistoryLoaded(true);
      });

    return () => abortController.abort();
  }, [chatId]);

  const handleNewChat = useCallback(async () => {
    try {
      const response = await fetch('/api/chats', { method: 'POST' });
      if (!response.ok) {
        throw new Error('Failed to create chat');
      }
      const chat: { id: string } = await response.json();
      router.push(`/chat/${chat.id}`);
    } catch (error) {
      console.error('Failed to create chat', error);
    }
  }, [router]);

  const handleSubmitMessage = useCallback(
    async (message: string) => {
      const title = message.trim().slice(0, 50);
      if (!title) {
        return;
      }

      try {
        const response = await fetch(`/api/chats/${chatId}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ title }),
        });
        if (!response.ok) {
          throw new Error('Failed to update chat title');
        }
        setSidebarRefreshToken((current) => current + 1);
      } catch (error) {
        console.error('Failed to update chat title', error);
      }
    },
    [chatId],
  );

  const MessagesComponent = useMemo(() => {
    function CopilotChatMessages(props: MessagesProps) {
      return (
        <ChatMessages
          {...props}
          chatId={chatId}
          historyLoaded={historyLoaded}
          persistedMessages={persistedMessages}
        />
      );
    }

    CopilotChatMessages.displayName = 'CopilotChatMessages';
    return CopilotChatMessages;
  }, [chatId, historyLoaded, persistedMessages]);

  return (
    <CopilotKit
      key={chatId}
      runtimeUrl="/api/copilotkit"
      agent="copilot"
      threadId={chatId}
    >
      <ChatToolCallRenderer />

      <SidebarProvider className="relative h-dvh overflow-hidden text-foreground">
        <AppSidebar
          activeChatId={chatId}
          onNewChat={handleNewChat}
          refreshToken={sidebarRefreshToken}
        />

        <SidebarInset>
          <SiteHeader breadcrumbs={breadcrumbs}>
            <Button
              className="md:hidden"
              onClick={() => void handleNewChat()}
              size="sm"
              type="button"
              variant="outline"
            >
              <MessageSquarePlus className="size-4" />
              <span>New chat</span>
            </Button>
          </SiteHeader>

          <div className="flex min-h-0 flex-1 flex-col p-3 md:p-4">
            <CopilotChat
              AssistantMessage={ChatAssistantMessage}
              Messages={MessagesComponent}
              className="smart-living-copilot-chat flex-1"
              labels={{
                title: 'Smart Living Copilot',
                initial: 'How can I help you with your smart home?',
                placeholder: 'Ask me anything...',
              }}
              onSubmitMessage={handleSubmitMessage}
            />
          </div>
        </SidebarInset>
      </SidebarProvider>
    </CopilotKit>
  );
}
