'use client';

import {
  ActionBarPrimitive,
  AuiIf,
  BranchPickerPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from '@assistant-ui/react';
import { MarkdownTextPrimitive } from '@assistant-ui/react-markdown';
import {
  ArrowDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  Pencil,
  RefreshCw,
  Square,
} from 'lucide-react';
import type { ComponentPropsWithoutRef, ReactNode } from 'react';
import type { ExtraProps } from 'react-markdown';

import {
  hasAssistantReloadAction,
  hasAssistantResponseActions,
} from '@/components/wotbot/assistant/message-actions';
import { markdownRemarkPlugins } from '@/components/wotbot/assistant/markdown';
import { WotbotToolCall } from '@/components/wotbot/assistant/tool-ui';
import { ThinkingIndicator } from '@/components/elements/thinking-indicator';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * The chat shell, composed from assistant-ui primitives.
 *
 * The primitives supply what would otherwise be hand-written and fiddly --
 * autoscroll that yields to the user, streaming part updates, edit/branch
 * bookkeeping, keyboard handling, accessibility -- while the markup and
 * styling stay ours, so this matches the existing design rather than importing
 * someone else's.
 */

/** Whether the composer holds a draft, deciding Send vs. the live-mode button. */
const hasDraft = (state: { thread: { composer: { text: string } } }) =>
  Boolean(state.thread.composer.text.trim());

function MarkdownTable({
  node,
  ...tableProps
}: ComponentPropsWithoutRef<'table'> & ExtraProps) {
  void node;
  return (
    <div
      className={cn(
        'not-prose my-4 overflow-x-auto rounded-md border border-border',
        '[&_table]:w-full [&_table]:min-w-[36rem] [&_table]:border-collapse [&_table]:text-left [&_table]:text-sm',
        '[&_th]:border-b [&_th]:bg-muted/60 [&_th]:px-3 [&_th]:py-2 [&_th]:font-semibold',
        '[&_td]:border-b [&_td]:px-3 [&_td]:py-2 [&_td]:align-top',
        '[&_tbody_tr:last-child_td]:border-b-0',
      )}
    >
      <table {...tableProps} />
    </div>
  );
}

function MarkdownText() {
  const isEmptyRunningPart = useAuiState(
    (state) =>
      state.part.type === 'text' &&
      state.part.status.type === 'running' &&
      state.part.text.length === 0,
  );

  if (isEmptyRunningPart) {
    return (
      <ThinkingIndicator aria-live="polite" label="Thinking" role="status" />
    );
  }

  return (
    <MarkdownTextPrimitive
      remarkPlugins={markdownRemarkPlugins}
      components={{ table: MarkdownTable }}
      className={cn(
        'wotbot-markdown prose prose-sm max-w-none break-words',
        '[&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-muted [&_pre]:p-3',
        '[&_code]:text-[0.9em]',
      )}
    />
  );
}

const assistantComponents = {
  Text: MarkdownText,
  tools: { Override: WotbotToolCall },
} as const;

function BranchPicker({ className }: { className?: string }) {
  return (
    <BranchPickerPrimitive.Root
      hideWhenSingleBranch
      className={cn(
        'flex items-center gap-1 text-xs text-muted-foreground',
        className,
      )}
    >
      <BranchPickerPrimitive.Previous asChild>
        <Button aria-label="Previous version" size="icon" variant="ghost">
          <ChevronLeft className="size-3.5" />
        </Button>
      </BranchPickerPrimitive.Previous>
      <span className="tabular-nums">
        <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
      </span>
      <BranchPickerPrimitive.Next asChild>
        <Button aria-label="Next version" size="icon" variant="ghost">
          <ChevronRight className="size-3.5" />
        </Button>
      </BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="group flex w-full flex-col items-end py-2">
      <div className="flex w-full items-center justify-end gap-1">
        {/* Editing forks the thread server-side, so the old answer is replaced
            rather than left sitting next to the new one. */}
        <ActionBarPrimitive.Root
          autohide="never"
          className="opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100"
        >
          <ActionBarPrimitive.Edit asChild>
            <Button aria-label="Edit message" size="icon" variant="ghost">
              <Pencil className="size-3.5" />
            </Button>
          </ActionBarPrimitive.Edit>
        </ActionBarPrimitive.Root>

        <div className="min-w-0 max-w-[80%] rounded-lg bg-muted px-4 py-2 text-foreground">
          <MessagePrimitive.Parts />
        </div>
      </div>
      <BranchPicker className="mt-1 mr-1" />
    </MessagePrimitive.Root>
  );
}

function EditComposer() {
  return (
    <ComposerPrimitive.Root className="my-2 w-full rounded-lg border border-border bg-background p-2">
      <ComposerPrimitive.Input
        autoFocus
        className="max-h-40 min-h-16 w-full resize-none bg-transparent text-sm outline-none"
      />
      <div className="flex justify-end gap-2 pt-2">
        <ComposerPrimitive.Cancel asChild>
          <Button size="sm" variant="ghost">
            Cancel
          </Button>
        </ComposerPrimitive.Cancel>
        <ComposerPrimitive.Send asChild>
          <Button size="sm">Save</Button>
        </ComposerPrimitive.Send>
      </div>
    </ComposerPrimitive.Root>
  );
}

/** Run-lifecycle lines in job transcripts; never present in chat threads. */
function SystemMessage() {
  return (
    <MessagePrimitive.Root className="flex w-full justify-center py-1">
      <div className="text-xs text-muted-foreground">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="group flex w-full flex-col items-start py-2">
      <div className="w-full min-w-0 text-foreground">
        <MessagePrimitive.Parts components={assistantComponents} />
      </div>
      <div className="mt-1 flex items-center gap-1">
        <AuiIf condition={hasAssistantResponseActions}>
          <ActionBarPrimitive.Root
            autohide="never"
            className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100"
          >
            <ActionBarPrimitive.Copy asChild>
              <Button aria-label="Copy response" size="icon" variant="ghost">
                <Copy className="size-3.5" />
              </Button>
            </ActionBarPrimitive.Copy>
            <AuiIf condition={hasAssistantReloadAction}>
              <ActionBarPrimitive.Reload asChild>
                <Button
                  aria-label="Regenerate response"
                  size="icon"
                  variant="ghost"
                >
                  <RefreshCw className="size-3.5" />
                </Button>
              </ActionBarPrimitive.Reload>
            </AuiIf>
          </ActionBarPrimitive.Root>
        </AuiIf>
        <BranchPicker />
      </div>
    </MessagePrimitive.Root>
  );
}

export function WotbotThread({
  actionSlot,
  className,
  emptyState,
  emptyComposerSlot,
  footer,
  placeholder = 'Type your message...',
}: {
  /** Controls rendered immediately before the shared Voice/Send slot. */
  actionSlot?: ReactNode;
  className?: string;
  emptyState?: ReactNode;
  /** Replaces Send while the composer has no draft (for example, Live mode). */
  emptyComposerSlot?: ReactNode;
  /** Replaces the composer entirely, for read-only transcripts. */
  footer?: ReactNode;
  placeholder?: string;
}) {
  return (
    <ThreadPrimitive.Root className={cn('flex min-h-0 flex-col', className)}>
      <ThreadPrimitive.Viewport className="relative flex min-h-0 flex-1 flex-col overflow-y-auto px-3">
        {emptyState ? (
          <ThreadPrimitive.Empty>{emptyState}</ThreadPrimitive.Empty>
        ) : null}

        <div className="mx-auto w-full max-w-3xl flex-1">
          <ThreadPrimitive.Messages
            components={{
              UserMessage,
              AssistantMessage,
              SystemMessage,
              EditComposer,
            }}
          />
        </div>

        <ThreadPrimitive.ScrollToBottom asChild>
          <Button
            aria-label="Scroll to bottom"
            className="sticky bottom-2 self-center rounded-full shadow-md disabled:invisible"
            size="icon"
            variant="outline"
          >
            <ArrowDown className="size-4" />
          </Button>
        </ThreadPrimitive.ScrollToBottom>
      </ThreadPrimitive.Viewport>

      {footer ?? (
        <ComposerPrimitive.Root className="mx-auto w-full max-w-3xl px-3 pb-3">
          <div className="rounded-lg border border-border bg-background px-3 py-2 shadow-sm">
            <ComposerPrimitive.Input
              autoFocus
              className="max-h-40 min-h-16 w-full resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              placeholder={placeholder}
              rows={2}
            />
            <div className="flex items-center justify-end gap-2 border-t border-border pt-2">
              {/* Send and Stop share a slot: the primitives render whichever
                matches the thread's running state. */}
              <div className="flex items-center gap-2">
                <ThreadPrimitive.If running={false}>
                  {actionSlot}
                  {emptyComposerSlot ? (
                    <>
                      <AuiIf condition={hasDraft}>
                        <ComposerPrimitive.Send asChild>
                          <Button type="submit">Send</Button>
                        </ComposerPrimitive.Send>
                      </AuiIf>
                      <AuiIf condition={(state) => !hasDraft(state)}>
                        {emptyComposerSlot}
                      </AuiIf>
                    </>
                  ) : (
                    <ComposerPrimitive.Send asChild>
                      <Button type="submit">Send</Button>
                    </ComposerPrimitive.Send>
                  )}
                </ThreadPrimitive.If>
                <ThreadPrimitive.If running>
                  <ComposerPrimitive.Cancel asChild>
                    <Button variant="secondary" type="button">
                      <Square className="mr-1 size-3" />
                      Stop
                    </Button>
                  </ComposerPrimitive.Cancel>
                </ThreadPrimitive.If>
              </div>
            </div>
          </div>
        </ComposerPrimitive.Root>
      )}
    </ThreadPrimitive.Root>
  );
}
