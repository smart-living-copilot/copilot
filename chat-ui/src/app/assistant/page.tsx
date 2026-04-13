'use client';

import {
  CopilotChat,
  CopilotKit,
} from '@copilotkit/react-core/v2';
import { LoaderCircle } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { chatToolCallRenderers } from '@/components/copilot/chat-tool-call-renderer';
import { MessageViewWithWotSummary } from '@/components/copilot/wot-interaction-summary';

function AssistantWelcomeScreen(props: Record<string, unknown>) {
  const input = props.input as ReactNode;
  const suggestionView = props.suggestionView as ReactNode;

  return (
    <div className="flex min-h-0 flex-1 items-center justify-center px-4 py-10">
      <div className="flex w-full max-w-3xl flex-col items-center gap-6 text-center">
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Assistant
          </h1>
          <p className="text-sm text-muted-foreground">
            Ask anything to start a new conversation.
          </p>
        </div>

        {input ? <div className="w-full">{input}</div> : null}
        {suggestionView ? <div className="w-full">{suggestionView}</div> : null}
      </div>
    </div>
  );
}

export default function AssistantPage() {
  const enableInspector =
    process.env.NEXT_PUBLIC_ENABLE_COPILOT_INSPECTOR === 'true';
  const [chatId, setChatId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const createChat = async () => {
      try {
        setError(null);
        setChatId(null);

        const response = await fetch('/api/chats', { method: 'POST' });
        if (!response.ok) {
          throw new Error('Failed to create chat');
        }

        const data = (await response.json()) as { id: string };
        if (!cancelled) {
          setChatId(data.id);
        }
      } catch (createError) {
        console.error('Failed to create assistant chat', createError);
        if (!cancelled) {
          setError('Could not create a new chat. Please try again.');
        }
      }
    };

    void createChat();

    return () => {
      cancelled = true;
    };
  }, []);

  const labels = useMemo(
    () => ({
      title: 'Assistant',
      chatInputPlaceholder: 'Type your message...',
    }),
    [],
  );

  if (error) {
    return (
      <div className="flex h-dvh items-center justify-center px-4">
        <div className="text-sm text-destructive">{error}</div>
      </div>
    );
  }

  if (!chatId) {
    return (
      <div className="flex h-dvh items-center justify-center text-muted-foreground">
        <LoaderCircle className="size-6 animate-spin" />
      </div>
    );
  }

  return (
    <CopilotKit
      key={chatId}
      runtimeUrl="/api/copilotkit"
      agent="copilot"
      threadId={chatId}
      enableInspector={enableInspector}
      renderToolCalls={chatToolCallRenderers}
    >
      <main className="assistant-shell flex h-dvh flex-col px-3 py-3 md:px-6 md:py-6">
        <div className="mx-auto flex w-full max-w-5xl min-h-0 flex-1 flex-col">
          <CopilotChat
            agentId="copilot"
            threadId={chatId}
            className="smart-living-copilot-chat assistant-minimal-chat flex-1"
            labels={labels}
            messageView={MessageViewWithWotSummary}
            welcomeScreen={AssistantWelcomeScreen}
          />
        </div>
      </main>
    </CopilotKit>
  );
}