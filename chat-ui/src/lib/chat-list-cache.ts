export interface ChatSummary {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

let cachedChats: ChatSummary[] | null = null;
let inflightChatListRequest: Promise<ChatSummary[]> | null = null;

function sortChatsByUpdatedAt(chats: ChatSummary[]) {
  return [...chats].sort((a, b) => {
    const updatedDiff =
      new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
    if (updatedDiff !== 0) {
      return updatedDiff;
    }

    return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
  });
}

export function getCachedChatList() {
  return cachedChats;
}

export function replaceCachedChatList(chats: ChatSummary[]) {
  cachedChats = sortChatsByUpdatedAt(chats);
  return cachedChats;
}

export function mutateCachedChatList(
  updater: (current: ChatSummary[]) => ChatSummary[],
) {
  cachedChats = sortChatsByUpdatedAt(updater(cachedChats ?? []));
  return cachedChats;
}

export function upsertCachedChat(chat: ChatSummary) {
  return mutateCachedChatList((current) => [
    chat,
    ...current.filter((currentChat) => currentChat.id !== chat.id),
  ]);
}

export function removeCachedChat(chatId: string) {
  return mutateCachedChatList((current) =>
    current.filter((chat) => chat.id !== chatId),
  );
}

export async function fetchChatList(options: { force?: boolean } = {}) {
  if (!options.force && cachedChats) {
    return cachedChats;
  }

  if (!options.force && inflightChatListRequest) {
    return inflightChatListRequest;
  }

  const request = fetch('/api/chats').then(async (response) => {
    if (!response.ok) {
      throw new Error('Failed to fetch chats');
    }

    return replaceCachedChatList((await response.json()) as ChatSummary[]);
  });

  const trackedRequest = request.finally(() => {
    if (inflightChatListRequest === trackedRequest) {
      inflightChatListRequest = null;
    }
  });
  inflightChatListRequest = trackedRequest;

  return inflightChatListRequest;
}
