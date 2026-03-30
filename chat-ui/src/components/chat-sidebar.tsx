'use client';

import { Fragment, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  Check,
  HouseWifi,
  LayoutDashboard,
  MessageSquarePlus,
  MoreHorizontal,
  Pencil,
  Search,
  Settings,
  Trash2,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarSeparator,
  useSidebar,
} from '@/components/ui/sidebar';
import { Spinner } from '@/components/ui/spinner';

const relativeTimeFormatter = new Intl.RelativeTimeFormat(undefined, {
  numeric: 'auto',
});

const shortDateFormatter = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
});

function formatUpdatedAt(updatedAt: string): string {
  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) {
    return 'Recently updated';
  }

  const diffMs = date.getTime() - Date.now();
  const absDiffMs = Math.abs(diffMs);

  if (absDiffMs < 60_000) {
    return 'Updated just now';
  }

  if (absDiffMs < 3_600_000) {
    return `Updated ${relativeTimeFormatter.format(
      Math.round(diffMs / 60_000),
      'minute',
    )}`;
  }

  if (absDiffMs < 86_400_000) {
    return `Updated ${relativeTimeFormatter.format(
      Math.round(diffMs / 3_600_000),
      'hour',
    )}`;
  }

  if (absDiffMs < 604_800_000) {
    return `Updated ${relativeTimeFormatter.format(
      Math.round(diffMs / 86_400_000),
      'day',
    )}`;
  }

  return `Updated ${shortDateFormatter.format(date)}`;
}

interface Chat {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

function getHistoryGroupLabel(updatedAt: string): string {
  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) {
    return 'Earlier';
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const updatedDay = new Date(date);
  updatedDay.setHours(0, 0, 0, 0);

  const diffDays = Math.floor(
    (today.getTime() - updatedDay.getTime()) / 86_400_000,
  );

  if (diffDays <= 0) {
    return 'Today';
  }

  if (diffDays === 1) {
    return 'Yesterday';
  }

  if (diffDays < 7) {
    return 'This week';
  }

  return 'Earlier';
}

interface AppSidebarProps {
  activeChatId?: string;
  onNewChat?: () => void | Promise<void>;
  refreshToken?: number;
}

export function AppSidebar({
  activeChatId,
  onNewChat,
  refreshToken = 0,
}: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const isOnChat = pathname.startsWith('/chat');
  const [chatList, setChatList] = useState<Chat[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreatingChat, setIsCreatingChat] = useState(false);
  const [deletingChatId, setDeletingChatId] = useState<string | null>(null);
  const [editingChatId, setEditingChatId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [historyQuery, setHistoryQuery] = useState('');
  const [savingChatId, setSavingChatId] = useState<string | null>(null);
  const { isMobile, setOpenMobile } = useSidebar();

  const normalizedHistoryQuery = historyQuery.trim().toLowerCase();
  const filteredChats = chatList.filter((chat) =>
    (chat.title || 'New Chat').toLowerCase().includes(normalizedHistoryQuery),
  );
  const groupedChats: Array<{ label: string; chats: Chat[] }> = [];

  for (const chat of filteredChats) {
    const label = getHistoryGroupLabel(chat.updatedAt);
    const existingGroup = groupedChats.find((group) => group.label === label);

    if (existingGroup) {
      existingGroup.chats.push(chat);
    } else {
      groupedChats.push({ label, chats: [chat] });
    }
  }

  const fetchChats = useCallback(async () => {
    setIsLoading(true);

    try {
      const response = await fetch('/api/chats');
      if (response.ok) {
        setChatList(await response.json());
      } else {
        throw new Error('Failed to fetch chats');
      }
    } catch (error) {
      console.error('Failed to fetch chats', error);
      toast.error('Could not load chat history.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchChats();
  }, [activeChatId, fetchChats, refreshToken]);

  const closeMobileSidebar = useCallback(() => {
    if (isMobile) {
      setOpenMobile(false);
    }
  }, [isMobile, setOpenMobile]);

  const handleDelete = async (chatId: string) => {
    const previousChatList = chatList;
    const deletingActiveChat = chatId === activeChatId;

    setDeletingChatId(chatId);
    setEditingChatId((current) => (current === chatId ? null : current));
    setChatList((current) => current.filter((chat) => chat.id !== chatId));

    try {
      const response = await fetch(`/api/chats/${chatId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error('Failed to delete chat');
      }
    } catch (error) {
      console.error('Failed to delete chat', error);
      setChatList(previousChatList);
      toast.error('Could not delete chat.');
      setDeletingChatId((current) => (current === chatId ? null : current));
      return;
    }

    if (deletingActiveChat) {
      try {
        if (onNewChat) {
          await onNewChat();
        } else {
          router.push('/chat');
        }
        closeMobileSidebar();
      } catch (error) {
        console.error('Deleted chat but failed to open a replacement', error);
        toast.error('Chat deleted, but opening the next chat failed.');
        router.push('/chat');
      }
    }

    setDeletingChatId((current) => (current === chatId ? null : current));
  };

  const handleSelectChat = (id: string) => {
    router.push(`/chat/${id}`);
    closeMobileSidebar();
  };

  const handleNewChat = async () => {
    if (isCreatingChat) {
      return;
    }

    setIsCreatingChat(true);
    setEditingChatId(null);

    if (onNewChat) {
      try {
        await onNewChat();
        closeMobileSidebar();
      } catch (error) {
        console.error('Failed to create chat', error);
        toast.error('Could not create chat.');
      } finally {
        setIsCreatingChat(false);
      }
    } else {
      // Fallback: create a chat and navigate
      try {
        const response = await fetch('/api/chats', { method: 'POST' });
        if (!response.ok) throw new Error('Failed to create chat');
        const chat: { id: string } = await response.json();
        router.push(`/chat/${chat.id}`);
        closeMobileSidebar();
      } catch (error) {
        console.error('Failed to create chat', error);
        toast.error('Could not create chat.');
      } finally {
        setIsCreatingChat(false);
      }
    }
  };

  const handleStartRename = useCallback((chat: Chat) => {
    setEditingChatId(chat.id);
    setEditingTitle(chat.title);
  }, []);

  const handleCancelRename = useCallback(() => {
    setEditingChatId(null);
    setEditingTitle('');
  }, []);

  const handleRename = useCallback(
    async (chatId: string) => {
      const title = editingTitle.trim().slice(0, 50);
      if (!title) {
        toast.error('Chat title cannot be empty.');
        return;
      }

      setSavingChatId(chatId);

      try {
        const response = await fetch(`/api/chats/${chatId}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ title, force: true }),
        });
        if (!response.ok) {
          throw new Error('Failed to rename chat');
        }

        const updatedAt = new Date().toISOString();
        setChatList((current) => {
          const updatedChat = current.find((chat) => chat.id === chatId);
          if (!updatedChat) {
            return current;
          }

          return [
            {
              ...updatedChat,
              title,
              updatedAt,
            },
            ...current.filter((chat) => chat.id !== chatId),
          ];
        });
        setEditingChatId(null);
        setEditingTitle('');
      } catch (error) {
        console.error('Failed to rename chat', error);
        toast.error('Could not rename chat.');
      } finally {
        setSavingChatId((current) => (current === chatId ? null : current));
      }
    },
    [editingTitle],
  );

  return (
    <Sidebar variant="floating" collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild size="lg" tooltip="Smart Living Copilot">
              <Link href="/">
                <div className="flex size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                  <HouseWifi className="size-4" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
                  <span className="truncate text-base font-semibold">
                    Smart Living Copilot
                  </span>
                  <span className="truncate text-xs">v0.0.1</span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Catalog</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  isActive={pathname.startsWith('/things')}
                  tooltip="Things"
                >
                  <Link href="/things">
                    <LayoutDashboard />
                    <span>Things</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Chat</SidebarGroupLabel>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={() => void handleNewChat()}
              disabled={isCreatingChat}
              tooltip="New chat"
            >
              {isCreatingChat ? (
                <Spinner className="size-4" />
              ) : (
                <MessageSquarePlus />
              )}
              <span>New chat</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>History</SidebarGroupLabel>
          <SidebarMenuSub>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <SidebarMenuSubItem key={i}>
                  <SidebarMenuSkeleton />
                </SidebarMenuSubItem>
              ))
            ) : chatList.length === 0 ? (
              <SidebarMenuSubItem>
                <SidebarMenuSubButton
                  className="h-auto items-start py-2"
                  onClick={() => void handleNewChat()}
                >
                  <div className="grid min-w-0 gap-0.5">
                    <span className="truncate font-medium">
                      Start your first chat
                    </span>
                    <span className="truncate text-[11px] text-muted-foreground">
                      Threads you open here will stay easy to pick up later.
                    </span>
                  </div>
                </SidebarMenuSubButton>
              </SidebarMenuSubItem>
            ) : filteredChats.length === 0 ? (
              <>
                <SidebarMenuSubItem className="pb-1">
                  <div className="relative">
                    <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      aria-label="Search chats"
                      className="bg-sidebar-accent/40 pl-8 pr-8 text-sm"
                      onChange={(event) => setHistoryQuery(event.target.value)}
                      placeholder="Search threads"
                      value={historyQuery}
                    />
                    {historyQuery ? (
                      <Button
                        className="absolute top-1/2 right-1 -translate-y-1/2"
                        onClick={() => setHistoryQuery('')}
                        size="icon-xs"
                        type="button"
                        variant="ghost"
                      >
                        <X className="size-3.5" />
                        <span className="sr-only">Clear search</span>
                      </Button>
                    ) : null}
                  </div>
                </SidebarMenuSubItem>
                <SidebarMenuSubItem>
                  <SidebarMenuSubButton aria-disabled className="h-auto py-2">
                    <div className="grid min-w-0 gap-0.5">
                      <span className="truncate font-medium">
                        No matching threads
                      </span>
                      <span className="truncate text-[11px] text-muted-foreground">
                        Try a different title or clear your search.
                      </span>
                    </div>
                  </SidebarMenuSubButton>
                </SidebarMenuSubItem>
              </>
            ) : (
              <>
                <SidebarMenuSubItem className="pb-1">
                  <div className="relative">
                    <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      aria-label="Search chats"
                      className="bg-sidebar-accent/40 pl-8 pr-8 text-sm"
                      onChange={(event) => setHistoryQuery(event.target.value)}
                      placeholder="Search threads"
                      value={historyQuery}
                    />
                    {historyQuery ? (
                      <Button
                        className="absolute top-1/2 right-1 -translate-y-1/2"
                        onClick={() => setHistoryQuery('')}
                        size="icon-xs"
                        type="button"
                        variant="ghost"
                      >
                        <X className="size-3.5" />
                        <span className="sr-only">Clear search</span>
                      </Button>
                    ) : null}
                  </div>
                </SidebarMenuSubItem>
                {groupedChats.map((group, index) => (
                  <Fragment key={group.label}>
                    <SidebarMenuSubItem
                      className={index === 0 ? 'px-2 pb-1' : 'px-2 pt-2 pb-1'}
                    >
                      <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                        {group.label}
                      </div>
                    </SidebarMenuSubItem>
                    {group.chats.map((chat) => (
                      <SidebarMenuSubItem key={chat.id}>
                        {editingChatId === chat.id ? (
                          <form
                            className="grid gap-2 rounded-md border border-sidebar-border bg-sidebar-accent/40 p-2"
                            onSubmit={(event) => {
                              event.preventDefault();
                              void handleRename(chat.id);
                            }}
                          >
                            <Input
                              autoFocus
                              disabled={savingChatId === chat.id}
                              maxLength={50}
                              onChange={(event) =>
                                setEditingTitle(event.target.value)
                              }
                              onKeyDown={(event) => {
                                if (event.key === 'Escape') {
                                  event.preventDefault();
                                  handleCancelRename();
                                }
                              }}
                              placeholder="Chat title"
                              value={editingTitle}
                            />
                            <div className="flex justify-end gap-1">
                              <Button
                                disabled={savingChatId === chat.id}
                                onClick={handleCancelRename}
                                size="icon-xs"
                                type="button"
                                variant="ghost"
                              >
                                <X />
                                <span className="sr-only">Cancel rename</span>
                              </Button>
                              <Button
                                disabled={
                                  savingChatId === chat.id ||
                                  !editingTitle.trim()
                                }
                                size="icon-xs"
                                type="submit"
                                variant="outline"
                              >
                                {savingChatId === chat.id ? (
                                  <Spinner />
                                ) : (
                                  <Check />
                                )}
                                <span className="sr-only">Save chat name</span>
                              </Button>
                            </div>
                          </form>
                        ) : (
                          <>
                            <SidebarMenuSubButton
                              className="h-auto items-start py-2 pr-7"
                              isActive={isOnChat && chat.id === activeChatId}
                              onClick={() => handleSelectChat(chat.id)}
                            >
                              <div className="grid min-w-0 flex-1 gap-0.5">
                                <span className="truncate font-medium">
                                  {chat.title || 'New Chat'}
                                </span>
                                <span className="truncate text-[11px] text-muted-foreground">
                                  {formatUpdatedAt(chat.updatedAt)}
                                </span>
                              </div>
                            </SidebarMenuSubButton>

                            {deletingChatId === chat.id ? (
                              <SidebarMenuAction disabled>
                                <Spinner className="size-3.5" />
                                <span className="sr-only">Deleting chat</span>
                              </SidebarMenuAction>
                            ) : (
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <SidebarMenuAction showOnHover>
                                    <MoreHorizontal />
                                    <span className="sr-only">More</span>
                                  </SidebarMenuAction>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent side="right" align="start">
                                  <DropdownMenuItem
                                    onSelect={(event) => {
                                      event.preventDefault();
                                      handleStartRename(chat);
                                    }}
                                  >
                                    <Pencil />
                                    <span>Rename chat</span>
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    onSelect={(event) => {
                                      event.preventDefault();
                                      void handleDelete(chat.id);
                                    }}
                                  >
                                    <Trash2 />
                                    <span>Delete chat</span>
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            )}
                          </>
                        )}
                      </SidebarMenuSubItem>
                    ))}
                  </Fragment>
                ))}
              </>
            )}
          </SidebarMenuSub>
        </SidebarGroup>

        <SidebarSeparator />
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              isActive={pathname.startsWith('/settings')}
              tooltip="Settings"
            >
              <Link href="/settings">
                <Settings />
                <span>Settings</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
