import { Fragment } from 'react';
import { Check, MoreHorizontal, Pencil, Trash2, X } from 'lucide-react';

import {
  formatUpdatedAt,
  groupChatsByUpdatedAt,
} from '@/components/chat-sidebar/formatters';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import {
  SidebarMenuAction,
  SidebarMenuSkeleton,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from '@/components/ui/sidebar';
import { Spinner } from '@/components/ui/spinner';
import { type ChatSummary } from '@/lib/chat-list-cache';

interface ChatHistoryListProps {
  activeChatId?: string;
  chatList: ChatSummary[];
  deletingChatId: string | null;
  editingChatId: string | null;
  editingTitle: string;
  isLoading: boolean;
  isOnChat: boolean;
  savingChatId: string | null;
  onCancelRename: () => void;
  onDelete: (chatId: string) => void;
  onEditingTitleChange: (title: string) => void;
  onFirstChat: () => void;
  onRename: (chatId: string) => void;
  onSelectChat: (chatId: string) => void;
  onStartRename: (chat: ChatSummary) => void;
}

export function ChatHistoryList({
  activeChatId,
  chatList,
  deletingChatId,
  editingChatId,
  editingTitle,
  isLoading,
  isOnChat,
  savingChatId,
  onCancelRename,
  onDelete,
  onEditingTitleChange,
  onFirstChat,
  onRename,
  onSelectChat,
  onStartRename,
}: ChatHistoryListProps) {
  if (isLoading) {
    return (
      <SidebarMenuSub>
        {Array.from({ length: 4 }).map((_, i) => (
          <SidebarMenuSubItem key={i}>
            <SidebarMenuSkeleton />
          </SidebarMenuSubItem>
        ))}
      </SidebarMenuSub>
    );
  }

  if (chatList.length === 0) {
    return (
      <SidebarMenuSub>
        <SidebarMenuSubItem>
          <SidebarMenuSubButton
            className="h-auto items-start py-2"
            onClick={onFirstChat}
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
      </SidebarMenuSub>
    );
  }

  return (
    <SidebarMenuSub>
      {groupChatsByUpdatedAt(chatList).map((group, index) => (
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
                <ChatRenameForm
                  chatId={chat.id}
                  editingTitle={editingTitle}
                  isSaving={savingChatId === chat.id}
                  onCancel={onCancelRename}
                  onChange={onEditingTitleChange}
                  onRename={onRename}
                />
              ) : (
                <ChatHistoryRow
                  active={isOnChat && chat.id === activeChatId}
                  chat={chat}
                  isDeleting={deletingChatId === chat.id}
                  onDelete={onDelete}
                  onSelect={onSelectChat}
                  onStartRename={onStartRename}
                />
              )}
            </SidebarMenuSubItem>
          ))}
        </Fragment>
      ))}
    </SidebarMenuSub>
  );
}

function ChatRenameForm({
  chatId,
  editingTitle,
  isSaving,
  onCancel,
  onChange,
  onRename,
}: {
  chatId: string;
  editingTitle: string;
  isSaving: boolean;
  onCancel: () => void;
  onChange: (title: string) => void;
  onRename: (chatId: string) => void;
}) {
  return (
    <form
      className="grid gap-2 rounded-md border border-sidebar-border bg-sidebar-accent/40 p-2"
      onSubmit={(event) => {
        event.preventDefault();
        onRename(chatId);
      }}
    >
      <Input
        autoFocus
        disabled={isSaving}
        maxLength={50}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.preventDefault();
            onCancel();
          }
        }}
        placeholder="Chat title"
        value={editingTitle}
      />
      <div className="flex justify-end gap-1">
        <Button
          disabled={isSaving}
          onClick={onCancel}
          size="icon-xs"
          type="button"
          variant="ghost"
        >
          <X />
          <span className="sr-only">Cancel rename</span>
        </Button>
        <Button
          disabled={isSaving || !editingTitle.trim()}
          size="icon-xs"
          type="submit"
          variant="outline"
        >
          {isSaving ? <Spinner /> : <Check />}
          <span className="sr-only">Save chat name</span>
        </Button>
      </div>
    </form>
  );
}

function ChatHistoryRow({
  active,
  chat,
  isDeleting,
  onDelete,
  onSelect,
  onStartRename,
}: {
  active: boolean;
  chat: ChatSummary;
  isDeleting: boolean;
  onDelete: (chatId: string) => void;
  onSelect: (chatId: string) => void;
  onStartRename: (chat: ChatSummary) => void;
}) {
  return (
    <>
      <SidebarMenuSubButton
        className="h-auto items-start py-2 pr-7"
        isActive={active}
        onClick={() => onSelect(chat.id)}
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

      {isDeleting ? (
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
                onStartRename(chat);
              }}
            >
              <Pencil />
              <span>Rename chat</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault();
                onDelete(chat.id);
              }}
            >
              <Trash2 />
              <span>Delete chat</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </>
  );
}
