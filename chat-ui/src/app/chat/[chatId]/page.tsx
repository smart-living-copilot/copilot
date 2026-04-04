'use client';

import {
  CopilotChat,
  CopilotKit,
  useAgent,
  UseAgentUpdate,
} from '@copilotkit/react-core/v2';
import type { Message } from '@copilotkit/shared';
import {
  MessageSquarePlus,
  Activity,
  Cloud,
  TrendingUp,
  Thermometer,
} from 'lucide-react';
import type { MutableRefObject, ReactNode } from 'react';
import { use, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AppSidebar } from '@/components/chat-sidebar';
import { chatToolCallRenderers } from '@/components/copilot/chat-tool-call-renderer';
import { MessageViewWithWotSummary } from '@/components/copilot/wot-interaction-summary';
import { WelcomeScreen } from '@/components/copilot/welcome-screen';
import { SiteHeader } from '@/components/site-header';
import { Button } from '@/components/ui/button';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import {
  normalizeSnapshotMessages,
  serializeSnapshotMessages,
} from '@/lib/chat-snapshots';

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

function flattenUserMessageContent(content: Message['content']) {
  if (typeof content === 'string') {
    return content;
  }

  if (!Array.isArray(content)) {
    return '';
  }

  return content
    .filter(
      (
        item,
      ): item is Extract<
        (typeof content)[number],
        { type: 'text'; text: string }
      > => item.type === 'text' && typeof item.text === 'string',
    )
    .map((item) => item.text)
    .join(' ')
    .trim();
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

function ChatExperience({
  breadcrumbs,
  chatId,
  examplePrompts,
  handleNewChat,
}: {
  breadcrumbs: { label: string; href: string }[];
  chatId: string;
  examplePrompts: {
    label: string;
    prompt: string;
    icon: ReactNode;
  }[];
  handleNewChat: () => Promise<void>;
}) {
  const { agent } = useAgent({
    agentId: 'copilot',
    updates: [
      UseAgentUpdate.OnMessagesChanged,
      UseAgentUpdate.OnRunStatusChanged,
    ],
  });
  const [loadedChatId, setLoadedChatId] = useState<string | null>(null);
  const [sidebarRefreshToken, setSidebarRefreshToken] = useState(0);
  const persistTimeoutRef = useRef<number | null>(null);
  const lastSavedPayloadRef = useRef<string | null>(null);
  const lastTitledUserMessageRef = useRef<string | null>(null);
  const historyLoaded = loadedChatId === chatId;

  useEffect(() => {
    const abortController = new AbortController();

    lastSavedPayloadRef.current = null;
    lastTitledUserMessageRef.current = null;
    agent.setMessages([]);

    void fetch(`/api/chats/${chatId}/messages`, {
      signal: abortController.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error('Failed to load chat messages');
        }

        const payload = (await response.json()) as { messages?: Message[] };
        const initialMessages = dedupeMessages(
          normalizeSnapshotMessages(payload.messages),
        );

        agent.setMessages(initialMessages);
        lastSavedPayloadRef.current =
          serializeSnapshotMessages(initialMessages).json;
        lastTitledUserMessageRef.current =
          [...initialMessages]
            .reverse()
            .find((message) => message.role === 'user')?.id ?? null;
        setLoadedChatId(chatId);
      })
      .catch((error) => {
        if (abortController.signal.aborted) {
          return;
        }

        console.error('Failed to load chat messages', error);
        setLoadedChatId(chatId);
      });

    return () => abortController.abort();
  }, [agent, chatId]);

  const messages = useMemo(
    () => dedupeMessages([...(agent.messages as Message[])]),
    [agent.messages],
  );

  useEffect(() => {
    if (!historyLoaded || agent.isRunning) {
      return;
    }

    if (persistTimeoutRef.current) {
      window.clearTimeout(persistTimeoutRef.current);
    }

    persistTimeoutRef.current = window.setTimeout(() => {
      const { json: payload, messages: normalizedMessages } =
        serializeSnapshotMessages(messages);
      if (payload !== lastSavedPayloadRef.current) {
        persistMessages(
          chatId,
          normalizedMessages,
          payload,
          lastSavedPayloadRef,
        );
      }
    }, 400);

    return () => {
      if (persistTimeoutRef.current) {
        window.clearTimeout(persistTimeoutRef.current);
      }
    };
  }, [agent.isRunning, chatId, historyLoaded, messages]);

  useEffect(() => {
    if (!historyLoaded || agent.isRunning) {
      return;
    }

    const latestUserMessage = [...messages]
      .reverse()
      .find((message) => message.role === 'user');
    if (
      !latestUserMessage ||
      latestUserMessage.id === lastTitledUserMessageRef.current
    ) {
      return;
    }

    const content = flattenUserMessageContent(latestUserMessage.content);
    const title = content.slice(0, 50);
    if (!title) {
      return;
    }

    lastTitledUserMessageRef.current = latestUserMessage.id;
    void fetch(`/api/chats/${chatId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ title }),
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error('Failed to update chat title');
        }
        setSidebarRefreshToken((current) => current + 1);
      })
      .catch((error) => {
        console.error('Failed to update chat title', error);
      });
  }, [agent.isRunning, chatId, historyLoaded, messages]);

  const chatLabels = useMemo(
    () => ({ chatInputPlaceholder: 'Ask me anything...' }),
    [],
  );
  const renderWelcomeScreen = useCallback(
    (props: Record<string, unknown>) => (
      <WelcomeScreen
        {...props}
        examplePrompts={examplePrompts}
        historyLoaded={historyLoaded}
      />
    ),
    [examplePrompts, historyLoaded],
  );

  return (
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
            agentId="copilot"
            threadId={chatId}
            className="smart-living-copilot-chat flex-1"
            labels={chatLabels}
            messageView={MessageViewWithWotSummary}
            welcomeScreen={renderWelcomeScreen}
          />
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

export default function ChatPage({
  params,
}: {
  params: Promise<{ chatId: string }>;
}) {
  const isProductionBuild = process.env.NODE_ENV === 'production';
  const { chatId } = use(params);
  const router = useRouter();

  const breadcrumbs = useMemo(() => [{ label: 'Chat', href: '/chat' }], []);

  const examplePrompts = useMemo(
    () => [
      {
        label: 'Kitchen temperature',
        prompt: 'Show me the current temperature in the kitchen',
        icon: <Thermometer className="size-4" />,
      },
      {
        label: 'Motion heatmap',
        prompt:
          'Create an hourly heatmap per room for the motion data of the last 24 hours',
        icon: <Activity className="size-4" />,
      },
      {
        label: 'Energy comparison',
        prompt:
          'Show the energy consumption of all households for the last 12 hours and compare them',
        icon: <TrendingUp className="size-4" />,
      },
      {
        label: 'CO2 forecast',
        prompt:
          'Create a forecast for the CO2 sensors for tomorrow for all rooms',
        icon: <Cloud className="size-4" />,
      },
    ],
    [],
  );

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

  return (
    <CopilotKit
      key={chatId}
      runtimeUrl="/api/copilotkit"
      agent="copilot"
      threadId={chatId}
      enableInspector={!isProductionBuild}
      renderToolCalls={chatToolCallRenderers}
    >
      <ChatExperience
        breadcrumbs={breadcrumbs}
        chatId={chatId}
        examplePrompts={examplePrompts}
        handleNewChat={handleNewChat}
      />
    </CopilotKit>
  );
}
