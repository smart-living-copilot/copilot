import { type ChatSummary, upsertCachedChat } from '@/lib/chat-list-cache';

export async function createChat(): Promise<ChatSummary> {
  const response = await fetch('/api/chats', { method: 'POST' });
  if (!response.ok) {
    throw new Error('Failed to create chat');
  }

  const chat = (await response.json()) as ChatSummary;
  upsertCachedChat(chat);
  return chat;
}
