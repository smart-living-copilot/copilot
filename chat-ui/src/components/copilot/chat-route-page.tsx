'use client';

import {
  CopilotChat,
  CopilotKit,
  useAgent,
  UseAgentUpdate,
} from '@copilotkit/react-core/v2';
import type { Message } from '@copilotkit/shared';
import {
  Activity,
  Cloud,
  LoaderCircle,
  MessageSquarePlus,
  Thermometer,
  TrendingUp,
} from 'lucide-react';
import {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useRouter } from 'next/navigation';
import { AppSidebar } from '@/components/chat-sidebar';
import { SiteHeader } from '@/components/site-header';
import { Button } from '@/components/ui/button';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { type ChatSummary, upsertCachedChat } from '@/lib/chat-list-cache';
import { createEmbedEphemeralChatId } from '@/lib/embed-chat';
import { chatToolCallRenderers } from './chat-tool-call-renderer';
import { type ExamplePrompt, WelcomeScreen } from './welcome-screen';
import { MessageViewWithWotSummary } from './wot-interaction-summary';

export type ChatRouteMode = 'full' | 'embed';

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

function useDefaultExamplePrompts(): ExamplePrompt[] {
  return useMemo(
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
}

function toQuerySuffix(queryString: string): string {
  return queryString ? `?${queryString}` : '';
}

function ChatAgentSync({
  chatId,
  onHistoryLoaded,
  onThreadUpdated,
}: {
  chatId: string;
  onHistoryLoaded: (chatId: string) => void;
  onThreadUpdated?: () => void;
}) {
  const { agent } = useAgent({
    agentId: 'copilot',
    updates: [
      UseAgentUpdate.OnMessagesChanged,
      UseAgentUpdate.OnRunStatusChanged,
    ],
  });
  const lastThreadSyncedMessageRef = useRef<string | null>(null);
  const historyLoadedRef = useRef(false);

  useEffect(() => {
    historyLoadedRef.current = false;

    const abortController = new AbortController();
    void fetch(`/api/chats/${chatId}`, {
      signal: abortController.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error('Failed to load chat');
        }
        const data = (await response.json()) as ChatSummary & {
          messages?: Message[];
        };
        upsertCachedChat({
          id: data.id,
          title: data.title,
          createdAt: data.createdAt,
          updatedAt: data.updatedAt,
        });
        const loaded = dedupeMessages(data.messages ?? []);
        if (loaded.length > 0) {
          agent.setMessages(loaded);
        }
        lastThreadSyncedMessageRef.current = loaded.at(-1)?.id ?? null;
      })
      .catch((error) => {
        if (!abortController.signal.aborted) {
          console.error('Failed to load chat', error);
        }
      })
      .finally(() => {
        if (!abortController.signal.aborted) {
          historyLoadedRef.current = true;
          onHistoryLoaded(chatId);
        }
      });

    return () => abortController.abort();
  }, [agent, chatId, onHistoryLoaded]);

  const rawMessages = useDeferredValue(agent.messages as Message[]);
  const messages = useMemo(
    () => dedupeMessages([...rawMessages]),
    [rawMessages],
  );

  useEffect(() => {
    if (agent.isRunning || !historyLoadedRef.current || !onThreadUpdated) {
      return;
    }

    const latestMessageId = messages.at(-1)?.id ?? null;
    if (
      !latestMessageId ||
      latestMessageId === lastThreadSyncedMessageRef.current
    ) {
      return;
    }

    lastThreadSyncedMessageRef.current = latestMessageId;
    onThreadUpdated();
  }, [agent.isRunning, messages, onThreadUpdated]);

  return null;
}

function FullChatExperience({
  chatId,
  handleNewChat,
}: {
  chatId: string;
  handleNewChat: () => Promise<ChatSummary | null>;
}) {
  const [loadedChatId, setLoadedChatId] = useState<string | null>(null);
  const [sidebarRefreshToken, setSidebarRefreshToken] = useState(0);
  const handleSidebarRefresh = useCallback(() => {
    setSidebarRefreshToken((current) => current + 1);
  }, []);
  const historyLoaded = loadedChatId === chatId;

  const breadcrumbs = useMemo(() => [{ label: 'Chat', href: '/chat' }], []);
  const examplePrompts = useDefaultExamplePrompts();
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
      <ChatAgentSync
        chatId={chatId}
        onHistoryLoaded={setLoadedChatId}
        onThreadUpdated={handleSidebarRefresh}
      />

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

function EmbedChatExperience({
  chatId,
  showExamplePrompts,
}: {
  chatId: string;
  showExamplePrompts: boolean;
}) {
  const cleanupRequestedRef = useRef(false);
  const examplePrompts = useDefaultExamplePrompts();

  const chatLabels = useMemo(
    () => ({
      title: 'Assistant',
      chatInputPlaceholder: 'Type your message...',
    }),
    [],
  );
  const renderWelcomeScreen = useCallback(
    (props: Record<string, unknown>) => (
      <WelcomeScreen
        {...props}
        examplePrompts={showExamplePrompts ? examplePrompts : []}
        historyLoaded
      />
    ),
    [examplePrompts, showExamplePrompts],
  );

  useEffect(() => {
    const cleanupSession = () => {
      if (cleanupRequestedRef.current) {
        return;
      }

      cleanupRequestedRef.current = true;
      void fetch(`/api/chats/${encodeURIComponent(chatId)}`, {
        method: 'DELETE',
        keepalive: true,
      }).catch(() => {
        // Ephemeral embed cleanup is best-effort only.
      });
    };

    window.addEventListener('pagehide', cleanupSession);
    window.addEventListener('beforeunload', cleanupSession);

    return () => {
      window.removeEventListener('pagehide', cleanupSession);
      window.removeEventListener('beforeunload', cleanupSession);
    };
  }, [chatId]);

  return (
    <main className="embed-chat-shell flex h-dvh flex-col px-3 py-3 md:px-6 md:py-6">
      <div className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col">
        <CopilotChat
          agentId="copilot"
          threadId={chatId}
          className="smart-living-copilot-chat embed-chat-frame flex-1"
          labels={chatLabels}
          messageView={MessageViewWithWotSummary}
          welcomeScreen={renderWelcomeScreen}
        />
      </div>
    </main>
  );
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
      const response = await fetch('/api/chats', { method: 'POST' });
      if (!response.ok) {
        throw new Error('Failed to create chat');
      }
      const chat = (await response.json()) as ChatSummary;
      upsertCachedChat(chat);
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

export function ChatIndexPage() {
  const router = useRouter();
  const [isCreatingChat, setIsCreatingChat] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const breadcrumbs = useMemo(() => [{ label: 'Chat' }], []);

  const handleNewChat = useCallback(async () => {
    if (isCreatingChat) {
      return null;
    }

    setIsCreatingChat(true);
    setError(null);

    try {
      const response = await fetch('/api/chats', { method: 'POST' });
      if (!response.ok) {
        throw new Error('Failed to create chat');
      }

      const chat = (await response.json()) as ChatSummary;
      upsertCachedChat(chat);
      router.push(`/chat/${chat.id}`);
      return chat;
    } catch (createError) {
      console.error('Failed to create chat', createError);
      setError('Could not create a new chat. Please try again.');
      return null;
    } finally {
      setIsCreatingChat(false);
    }
  }, [isCreatingChat, router]);

  return (
    <SidebarProvider className="relative h-dvh overflow-hidden text-foreground">
      <AppSidebar onNewChat={handleNewChat} />

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

        <div className="flex min-h-0 flex-1 items-center justify-center p-6 md:p-8">
          <div className="mx-auto max-w-lg space-y-4 text-center">
            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight text-foreground">
                No chat selected
              </h1>
              <p className="text-sm leading-6 text-muted-foreground md:text-base">
                Start a new conversation or pick an existing thread from the
                history in the sidebar.
              </p>
            </div>

            <div className="flex justify-center">
              <Button
                onClick={() => void handleNewChat()}
                disabled={isCreatingChat}
                size="lg"
                type="button"
              >
                {isCreatingChat ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <MessageSquarePlus className="size-4" />
                )}
                {isCreatingChat ? 'Creating chat...' : 'Start a new chat'}
              </Button>
            </div>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
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
