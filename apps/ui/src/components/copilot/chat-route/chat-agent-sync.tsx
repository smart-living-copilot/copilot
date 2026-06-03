import { useAgent, UseAgentUpdate } from '@copilotkit/react-core/v2';
import type { Message } from '@copilotkit/shared';
import { useDeferredValue, useEffect, useMemo, useRef } from 'react';

import { dedupeMessages } from '@/components/copilot/chat-route/chat-message-utils';
import { type ChatSummary, upsertCachedChat } from '@/lib/chat-list-cache';

export function ChatAgentSync({
  chatId,
  onHistoryLoaded,
  onMessagesLoaded,
  onThreadUpdated,
  refreshToken = 0,
}: {
  chatId: string;
  onHistoryLoaded: (chatId: string) => void;
  onMessagesLoaded?: (messages: Message[]) => void;
  onThreadUpdated?: () => void;
  refreshToken?: number;
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
        onMessagesLoaded?.(loaded);
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
  }, [agent, chatId, onHistoryLoaded, onMessagesLoaded, refreshToken]);

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
