'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { History, MessageSquareWarning, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { fetchChatList, type ChatSummary } from '@/lib/chat-list-cache';
import {
  selectChatsForBatchDeletion,
  type ChatBatchDeleteRequest,
} from '@/lib/chat-deletion';
import { httpJson } from '@/lib/http-client';

const CONFIRM_TEXT = 'DELETE';
const QUICK_CUTOFF_OPTIONS = [
  { label: 'Yesterday', daysAgo: 1 },
  { label: '7 days ago', daysAgo: 7 },
  { label: '30 days ago', daysAgo: 30 },
  { label: '90 days ago', daysAgo: 90 },
] as const;

interface BatchDeleteResponse {
  deleted: number;
}

function formatChatCount(count: number) {
  return `${count} chat${count === 1 ? '' : 's'}`;
}

function formatDateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getTodayDateInputValue() {
  return formatDateInputValue(new Date());
}

function getDateInputValueDaysAgo(daysAgo: number) {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  return formatDateInputValue(date);
}

function dateInputToEndOfDayIso(value: string) {
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) {
    return null;
  }

  const date = new Date(year, month - 1, day, 23, 59, 59, 999);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

async function deleteChats(request: ChatBatchDeleteRequest) {
  return httpJson<BatchDeleteResponse>('/chats', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
}

export function ChatCleanupPanel() {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [cutoffDate, setCutoffDate] = useState('');
  const [deleteAllDialogOpen, setDeleteAllDialogOpen] = useState(false);
  const [deleteBeforeDialogOpen, setDeleteBeforeDialogOpen] = useState(false);
  const [confirmDeleteAllText, setConfirmDeleteAllText] = useState('');
  const [confirmDeleteBeforeText, setConfirmDeleteBeforeText] = useState('');
  const [deletingAll, setDeletingAll] = useState(false);
  const [deletingBefore, setDeletingBefore] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const loadChats = useCallback(async (force = false) => {
    setIsLoading(true);
    try {
      setChats(await fetchChatList({ force }));
    } catch (error) {
      console.error('Failed to load chats for cleanup', error);
      toast.error('Could not load chats.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadChats();
  }, [loadChats]);

  const cutoffIso = useMemo(
    () => dateInputToEndOfDayIso(cutoffDate),
    [cutoffDate],
  );
  const cutoffMatches = useMemo(
    () =>
      cutoffIso
        ? selectChatsForBatchDeletion(chats, {
            mode: 'before',
            before: cutoffIso,
          })
        : [],
    [chats, cutoffIso],
  );

  const refreshAfterDelete = async () => {
    const refreshedChats = await fetchChatList({ force: true });
    setChats(refreshedChats);
  };

  const openDeleteAllDialog = () => {
    setConfirmDeleteAllText('');
    setDeleteAllDialogOpen(true);
  };

  const openDeleteBeforeDialog = () => {
    setConfirmDeleteBeforeText('');
    setDeleteBeforeDialogOpen(true);
  };

  const handleDeleteAll = async () => {
    if (confirmDeleteAllText !== CONFIRM_TEXT) {
      return;
    }

    setDeletingAll(true);
    try {
      const result = await deleteChats({ mode: 'all' });
      setDeleteAllDialogOpen(false);
      await refreshAfterDelete();
      toast.success(`${formatChatCount(result.deleted)} deleted.`);
    } catch (error) {
      console.error('Failed to delete all chats', error);
      toast.error(
        error instanceof Error ? error.message : 'Could not delete chats.',
      );
      await loadChats(true);
    } finally {
      setDeletingAll(false);
    }
  };

  const handleDeleteBefore = async () => {
    if (confirmDeleteBeforeText !== CONFIRM_TEXT || !cutoffIso) {
      return;
    }

    setDeletingBefore(true);
    try {
      const result = await deleteChats({
        mode: 'before',
        before: cutoffIso,
      });
      setDeleteBeforeDialogOpen(false);
      await refreshAfterDelete();
      toast.success(
        result.deleted > 0
          ? `${formatChatCount(result.deleted)} deleted.`
          : 'No chats matched the selected date.',
      );
    } catch (error) {
      console.error('Failed to delete chats up to date', error);
      toast.error(
        error instanceof Error ? error.message : 'Could not delete chats.',
      );
      await loadChats(true);
    } finally {
      setDeletingBefore(false);
    }
  };

  const hasChats = chats.length > 0;
  const loadingCount = isLoading && chats.length === 0;
  const countLabel = loadingCount
    ? 'Loading chat count...'
    : `${formatChatCount(chats.length)} saved in the sidebar.`;
  const deleteBeforeCountLabel = cutoffIso
    ? `${formatChatCount(cutoffMatches.length)} matched.`
    : 'Select a date to preview the matching chats.';

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <MessageSquareWarning className="size-5 text-muted-foreground" />
            <h3 className="text-lg font-medium">Chat data</h3>
          </div>
          <p className="text-sm text-muted-foreground">
            Delete saved Copilot chat history and related execution sessions.
          </p>
        </div>

        <Separator />

        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <div className="rounded-lg border bg-muted/30 p-4">
              <p className="text-sm font-medium">Saved chats</p>
              <p className="mt-2 text-2xl font-semibold tracking-tight">
                {loadingCount ? '...' : chats.length}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{countLabel}</p>
            </div>

            <div className="rounded-lg border border-destructive/25 bg-destructive/5 p-4">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Badge variant="destructive">Danger zone</Badge>
                  <p className="text-sm font-medium">Delete chat history</p>
                </div>
                <p className="text-sm text-muted-foreground">
                  Batch deletion permanently removes selected chats from the
                  Copilot thread store and clears their code execution sessions.
                </p>
              </div>

              <Separator className="my-4" />

              <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                <Button
                  disabled={
                    loadingCount || !hasChats || deletingAll || deletingBefore
                  }
                  onClick={openDeleteBeforeDialog}
                  variant="outline"
                >
                  <History className="size-4" />
                  Delete up to date
                </Button>
                <Button
                  disabled={
                    loadingCount || !hasChats || deletingAll || deletingBefore
                  }
                  onClick={openDeleteAllDialog}
                  variant="destructive"
                >
                  <Trash2 className="size-4" />
                  Delete all
                </Button>
              </div>
            </div>
          </div>

          {!hasChats && !loadingCount ? (
            <Alert>
              <AlertTitle>No saved chats</AlertTitle>
              <AlertDescription>
                There is no chat history to clean up right now.
              </AlertDescription>
            </Alert>
          ) : null}
        </div>
      </section>

      <Dialog
        open={deleteBeforeDialogOpen}
        onOpenChange={setDeleteBeforeDialogOpen}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete chats up to date</DialogTitle>
            <DialogDescription>
              Choose the latest updated date to remove. This action cannot be
              undone.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <label
              className="text-sm font-medium"
              htmlFor="delete-before-date-input"
            >
              Delete chats updated on or before
            </label>
            <Input
              autoComplete="off"
              id="delete-before-date-input"
              max={getTodayDateInputValue()}
              onChange={(event) => setCutoffDate(event.target.value)}
              type="date"
              value={cutoffDate}
            />
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {QUICK_CUTOFF_OPTIONS.map((option) => {
                const value = getDateInputValueDaysAgo(option.daysAgo);
                const selected = cutoffDate === value;

                return (
                  <Button
                    key={option.daysAgo}
                    onClick={() => setCutoffDate(value)}
                    size="sm"
                    type="button"
                    variant={selected ? 'secondary' : 'outline'}
                  >
                    {option.label}
                  </Button>
                );
              })}
            </div>
            <p className="text-xs text-muted-foreground">
              {deleteBeforeCountLabel}
            </p>
          </div>
          <div className="space-y-2">
            <label
              className="text-sm font-medium"
              htmlFor="delete-before-confirm-input"
            >
              Type {CONFIRM_TEXT} to confirm
            </label>
            <Input
              autoComplete="off"
              id="delete-before-confirm-input"
              onChange={(event) =>
                setConfirmDeleteBeforeText(event.target.value)
              }
              value={confirmDeleteBeforeText}
            />
          </div>
          <DialogFooter>
            <Button
              disabled={deletingBefore}
              onClick={() => setDeleteBeforeDialogOpen(false)}
              variant="outline"
            >
              Cancel
            </Button>
            <Button
              disabled={
                confirmDeleteBeforeText !== CONFIRM_TEXT ||
                !cutoffIso ||
                cutoffMatches.length === 0 ||
                deletingBefore
              }
              onClick={() => void handleDeleteBefore()}
              variant="destructive"
            >
              {deletingBefore ? 'Deleting...' : 'Delete chats'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteAllDialogOpen} onOpenChange={setDeleteAllDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete all chats</DialogTitle>
            <DialogDescription>
              This removes all {formatChatCount(chats.length)}. Type{' '}
              {CONFIRM_TEXT} to confirm.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <label
              className="text-sm font-medium"
              htmlFor="delete-all-confirm-input"
            >
              Type {CONFIRM_TEXT} to confirm
            </label>
            <Input
              autoComplete="off"
              autoFocus
              id="delete-all-confirm-input"
              onChange={(event) => setConfirmDeleteAllText(event.target.value)}
              value={confirmDeleteAllText}
            />
          </div>
          <DialogFooter>
            <Button
              disabled={deletingAll}
              onClick={() => setDeleteAllDialogOpen(false)}
              variant="outline"
            >
              Cancel
            </Button>
            <Button
              disabled={confirmDeleteAllText !== CONFIRM_TEXT || deletingAll}
              onClick={() => void handleDeleteAll()}
              variant="destructive"
            >
              {deletingAll ? 'Deleting...' : 'Delete all'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
