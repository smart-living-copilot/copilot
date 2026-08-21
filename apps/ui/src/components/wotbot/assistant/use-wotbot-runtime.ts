'use client';

import {
  useExternalStoreRuntime,
  type ThreadMessageLike,
} from '@assistant-ui/react';
import {
  FetchStreamTransport,
  useStream,
} from '@langchain/langgraph-sdk/react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { findRetryTarget } from '@/components/wotbot/assistant/message-actions';
import { toThreadMessages, type LangChainMessage } from '@/lib/thread-messages';

type WotbotState = {
  messages: LangChainMessage[];
  reasoning_effort?: string;
};

function appendedText(content: readonly { type: string }[]): string {
  return content
    .filter(
      (part): part is { type: 'text'; text: string } => part.type === 'text',
    )
    .map((part) => part.text)
    .join('\n')
    .trim();
}

/**
 * Bridges LangGraph's `useStream` into assistant-ui.
 *
 * `useStream` owns the transport and the message state; assistant-ui only
 * renders. `useExternalStoreRuntime` reflects state we already hold rather than
 * keeping its own copy, so there is no second source of truth to reconcile and
 * nothing that can synthesize an event out of order.
 */
export type ThreadHistory = {
  loaded: boolean;
  values: WotbotState;
};

const EMPTY_HISTORY: WotbotState = { messages: [] };

/**
 * Loads a thread's persisted state.
 *
 * Kept separate from the runtime because `useStream` reads `initialValues`
 * when it mounts and does not adopt a later change: seeding it after the fetch
 * resolves leaves the thread permanently empty. Callers therefore wait for
 * `loaded` before mounting the runtime.
 *
 * A custom transport has no `fetchStateHistory`, so this is where history
 * comes from at all.
 */
export function useThreadHistory(threadId: string): ThreadHistory {
  // Keyed by threadId so switching threads derives "not loaded yet" rather
  // than resetting state imperatively inside the effect.
  const [history, setHistory] = useState<{
    threadId: string;
    values: WotbotState;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;

    void fetch(`/api/chat/${encodeURIComponent(threadId)}/state`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data: { values?: WotbotState } | null) => {
        if (cancelled) return;
        setHistory({ threadId, values: data?.values ?? EMPTY_HISTORY });
      })
      .catch(() => {
        if (cancelled) return;
        // Start empty rather than block the thread on a failed read.
        setHistory({ threadId, values: EMPTY_HISTORY });
      });

    return () => {
      cancelled = true;
    };
  }, [threadId]);

  return history?.threadId === threadId
    ? { loaded: true, values: history.values }
    : { loaded: false, values: EMPTY_HISTORY };
}

export function useWotbotRuntime({
  threadId,
  initialValues,
  reasoningEffort,
  onThreadUpdated,
}: {
  threadId: string;
  /** Must be the already-loaded history; see `useThreadHistory`. */
  initialValues: WotbotState;
  reasoningEffort?: string;
  onThreadUpdated?: () => void;
}) {
  const transport = useMemo(
    () =>
      new FetchStreamTransport<WotbotState>({
        apiUrl: `/api/chat/${encodeURIComponent(threadId)}/stream`,
      }),
    [threadId],
  );

  const stream = useStream<WotbotState>({
    transport,
    threadId,
    initialValues,
    onFinish: () => onThreadUpdated?.(),
  });

  // `stream.messages` is empty until a run produces values -- `initialValues`
  // seeds what gets submitted, not what is displayed -- so loaded history is
  // what renders until then. Once a run starts, the backend's `values` frames
  // carry the full accumulated state, so the stream becomes authoritative and
  // this falls away.
  const messages = useMemo(() => {
    const streamed = stream.messages as LangChainMessage[] | undefined;
    const source = streamed?.length ? streamed : initialValues.messages;
    return toThreadMessages(source);
  }, [initialValues.messages, stream.messages]);

  const submitText = useCallback(
    (text: string) => {
      if (!text) return;
      stream.submit({
        messages: [{ type: 'human', content: text }],
        // Plain graph state. The AG-UI stack needed a forwardedProps hack here
        // to beat CopilotKit's state-merge ordering; nothing to beat now.
        ...(reasoningEffort ? { reasoning_effort: reasoningEffort } : {}),
      } as Partial<WotbotState>);
    },
    [reasoningEffort, stream],
  );

  /**
   * Editing a turn must replace it, not append beside it.
   *
   * LangGraph checkpoints are append-only, so the backend forks history to
   * just before the edited message first; the run that follows then continues
   * from that fork. The authoritative `values` frame it emits replaces the
   * client's message list, which is what makes the superseded answer vanish.
   *
   * The AG-UI adapter did this implicitly by detecting "same id, different
   * content"; with it gone, the fork is an explicit call.
   */
  const editAndResubmit = useCallback(
    async (sourceId: string | null, text: string) => {
      if (!text) return;
      if (sourceId) {
        try {
          await fetch(`/api/chat/${encodeURIComponent(threadId)}/fork`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message_id: sourceId }),
          });
        } catch {
          // Fall through and append: a failed fork should not swallow the edit.
        }
      }
      submitText(text);
    },
    [submitText, threadId],
  );

  const cancel = useCallback(async () => {
    stream.stop();
    // The abort does propagate now that nothing buffers between the browser and
    // the backend, but ask explicitly too: this is the call that never existed
    // before, and it is what actually stops the graph rather than just the
    // client's view of it.
    await fetch(`/api/chat/${encodeURIComponent(threadId)}/cancel`, {
      method: 'POST',
    }).catch(() => {
      // Best-effort; the abort above already stopped the client stream.
    });
  }, [stream, threadId]);

  const runtime = useExternalStoreRuntime<ThreadMessageLike>({
    messages,
    isRunning: stream.isLoading,
    // Deliberately NOT gating on history loading: `isLoading` disables the
    // composer, so a slow or failed state fetch would leave the user unable to
    // type at all. History is only a seed -- the graph appends to the
    // checkpointed thread server-side regardless -- so the welcome screen
    // surfaces the loading state instead (see `historyLoaded`).
    convertMessage: (message) => message,
    onNew: async (message) => {
      submitText(appendedText(message.content));
    },
    onEdit: async (message) => {
      await editAndResubmit(message.sourceId, appendedText(message.content));
    },
    onReload: async (parentId) => {
      const target = findRetryTarget(messages, parentId);
      if (target) {
        await editAndResubmit(target.sourceId, target.text);
      }
    },
    onCancel: cancel,
  });

  return { runtime, stream, submitText };
}
