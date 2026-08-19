'use client';

import {
  useCallback,
  useState,
  type ComponentProps,
  type KeyboardEvent,
} from 'react';
import {
  CopilotChatUserMessage,
  useAgent,
  useCopilotKit,
  UseAgentUpdate,
} from '@copilotkit/react-core/v2';
import type { Message } from '@copilotkit/shared';

import {
  flattenUserMessageContent,
  hasEditableChange,
  messagesAfterEdit,
} from '@/components/wotbot/chat-route/chat-message-utils';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

type UserMessageProps = ComponentProps<typeof CopilotChatUserMessage>;

/**
 * Drop-in replacement for CopilotKit's default `userMessage` slot that turns
 * on its (otherwise unwired) edit affordance: editing a message discards it
 * and everything the agent said/did afterward, then reruns from the edited
 * content. There's no branch history kept -- the discarded turn is gone, not
 * navigable back to. The actual removal happens server-side, via
 * `ag_ui_langgraph`'s built-in same-id-edit detection forking the LangGraph
 * checkpoint (see messagesAfterEdit for why the id has to stay the same).
 *
 * This has to own the agent/regenerate logic itself: CopilotChatMessageView
 * only ever passes this slot a bare `message` prop (see MemoizedUserMessage
 * in its source), not the full message list or the agent, so there's no
 * prop channel to receive them through.
 */
function UserMessageWithEditImpl({ message, ...props }: UserMessageProps) {
  const { agent } = useAgent({
    agentId: 'wotbot',
    updates: [
      UseAgentUpdate.OnMessagesChanged,
      UseAgentUpdate.OnRunStatusChanged,
    ],
  });
  const { copilotkit } = useCopilotKit();
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [draft, setDraft] = useState('');

  const startEdit = useCallback(() => {
    setDraft(flattenUserMessageContent(message.content));
    setIsEditing(true);
  }, [message.content]);

  const cancelEdit = useCallback(() => setIsEditing(false), []);

  const saveEdit = useCallback(async () => {
    // Re-entrancy guard: a fast double-Enter/double-click before agent.isRunning
    // has flipped could otherwise fire this twice. The second call would see
    // its own just-submitted edit already sitting in the checkpoint with
    // identical content -- the same "looks unchanged" case hasEditableChange
    // guards below -- and produce a duplicate response the same way.
    if (isSaving || !hasEditableChange(message.content, draft)) {
      return;
    }

    setIsSaving(true);
    try {
      agent.setMessages(
        messagesAfterEdit(
          agent.messages as Message[],
          message.id,
          draft.trim(),
        ),
      );
      setIsEditing(false);
      await copilotkit.runAgent({ agent });
    } catch (error) {
      console.error('Failed to regenerate after editing message', error);
    } finally {
      setIsSaving(false);
    }
  }, [agent, copilotkit, draft, isSaving, message.content, message.id]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        void saveEdit();
      } else if (event.key === 'Escape') {
        cancelEdit();
      }
    },
    [cancelEdit, saveEdit],
  );

  if (isEditing) {
    return (
      <div
        className="flex flex-col items-end gap-2 pt-10"
        data-copilotkit
        data-testid="copilot-user-message-editing"
      >
        <Textarea
          autoFocus
          className="max-w-[80%] min-w-60"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          value={draft}
        />
        <div className="flex items-center gap-2">
          <Button onClick={cancelEdit} size="sm" type="button" variant="ghost">
            Cancel
          </Button>
          <Button
            disabled={
              !hasEditableChange(message.content, draft) ||
              agent.isRunning ||
              isSaving
            }
            onClick={() => void saveEdit()}
            size="sm"
            type="button"
          >
            Send
          </Button>
        </div>
      </div>
    );
  }

  return (
    <CopilotChatUserMessage
      {...props}
      message={message}
      onEditMessage={agent.isRunning ? undefined : startEdit}
    />
  );
}

// CopilotChatMessageView's `userMessage` slot expects the CopilotChatUserMessage
// type shape, statics included (Container, MessageRenderer, ...) -- same
// pattern AssistantMessageWithWotSummary uses below for the assistant slot.
export const UserMessageWithEdit = Object.assign(
  UserMessageWithEditImpl,
  CopilotChatUserMessage,
);
