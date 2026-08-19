import { randomUUID, type Message } from '@copilotkit/shared';

import {
  normalizeRunCodeResult,
  type RunCodeArtifact,
} from '@/components/wotbot/chat-tool-call-model';

export function dedupeMessages(messages: Message[]): Message[] {
  const latestById = new Map<string, Message>();
  for (const message of messages) {
    latestById.set(message.id, message);
  }

  const deduped: Message[] = [];
  const seen = new Set<string>();
  for (const message of messages) {
    const latest = latestById.get(message.id);
    if (!latest || seen.has(latest.id)) {
      continue;
    }
    seen.add(latest.id);
    deduped.push(latest);
  }

  return deduped;
}

function getMessageRole(message: Message) {
  return typeof message.role === 'string' ? message.role : '';
}

function getMessageContent(message: Message) {
  return (message as { content?: unknown }).content;
}

type UserMessageContent =
  | string
  | Array<{ type: string; text?: string }>
  | undefined;

/** Flattens a user message's content (plain string, or an array of content
 * parts) down to the editable text a plain <textarea> can hold. Non-text
 * parts (e.g. images) are dropped -- editing only round-trips the text. */
export function flattenUserMessageContent(content: UserMessageContent): string {
  if (!content) {
    return '';
  }
  if (typeof content === 'string') {
    return content;
  }
  return content
    .map((part) => (part.type === 'text' ? (part.text ?? '') : ''))
    .filter((text) => text.length > 0)
    .join('\n');
}

/** Whether saving this edit would actually change the message.
 *
 * ag_ui_langgraph's edit detection is a byte-for-byte content compare with
 * no trimming (`_normalized_content`) -- if the trimmed draft comes back
 * identical to the original, it doesn't look like an edit to the backend at
 * all. That request then falls through to the adapter's plain continuation
 * path (same id already in checkpoint -> nothing "new" to merge), and the
 * graph runs again from unchanged state anyway, appending a second, harmless
 * -looking but duplicate response next to the one already there. Skipping
 * the save when nothing changed avoids sending a request that would hit
 * that path. */
export function hasEditableChange(
  originalContent: UserMessageContent,
  draft: string,
): boolean {
  const trimmed = draft.trim();
  return (
    trimmed.length > 0 && trimmed !== flattenUserMessageContent(originalContent)
  );
}

/** The message list to send after editing `editedMessageId` to `newContent`.
 *
 * The edited message keeps its ORIGINAL id -- that's load-bearing, not
 * incidental. The AG-UI/LangGraph bridge (`ag_ui_langgraph`'s
 * `_detect_edited_human_message`) recognizes an edit specifically as "same
 * id, different content" and, on seeing one, forks the LangGraph checkpoint
 * to right before that message and regenerates from there
 * (`prepare_regenerate_stream`, using LangGraph's real time-travel:
 * `get_checkpoint_before_message` + `graph.aupdate_state(..., as_node=...)`).
 * That's what actually removes the old response from the thread -- give the
 * edited message a new id instead and the adapter can't tell it apart from
 * an unrelated new message, falls back to its plain additive merge, and the
 * old and new turns end up persisted side by side (see git history on this
 * function for that bug).
 *
 * Messages after the edited one are dropped here too, but only for
 * optimistic client-side UI -- the adapter ignores anything past the edited
 * message once it takes the regenerate path, so this half is cosmetic, not
 * what makes the old turn disappear. */
export function messagesAfterEdit(
  messages: Message[],
  editedMessageId: string,
  newContent: string,
): Message[] {
  const editedIndex = messages.findIndex(
    (message) => message.id === editedMessageId,
  );
  if (editedIndex === -1) {
    // Shouldn't normally happen (the message being edited came from this
    // same list) -- fall back to sending it as a new message rather than
    // silently dropping the edit.
    return [
      ...messages,
      { id: randomUUID(), role: 'user', content: newContent },
    ];
  }
  const edited = { ...messages[editedIndex], content: newContent };
  return [...messages.slice(0, editedIndex), edited];
}

export function getLatestTurnArtifacts(messages: Message[]): RunCodeArtifact[] {
  let lastUserIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (getMessageRole(messages[index]) === 'user') {
      lastUserIndex = index;
      break;
    }
  }

  if (lastUserIndex < 0) {
    return [];
  }

  const artifacts: RunCodeArtifact[] = [];
  const seen = new Set<string>();

  for (const message of messages.slice(lastUserIndex + 1)) {
    if (getMessageRole(message) !== 'tool') {
      continue;
    }

    const result = normalizeRunCodeResult(getMessageContent(message));
    for (const artifact of result.artifacts ?? []) {
      const key = `${artifact.kind}:${artifact.filename}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      artifacts.push(artifact);
    }
  }

  return artifacts;
}
