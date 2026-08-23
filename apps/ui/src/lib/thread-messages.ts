import type { ThreadMessageLike } from '@assistant-ui/react';

import {
  looksLikeDeviceInteractionSummaryContent,
  parseDeviceInteractionSummaryContent,
} from '@/lib/wot-interactions';

/**
 * Converts LangChain messages (as they arrive over the wire from LangGraph)
 * into assistant-ui's `ThreadMessageLike`.
 *
 * The one piece of real translation in the chat stack. Two things make it more
 * than a field rename:
 *
 * 1. LangChain models a tool result as its own `tool` message following the
 *    `ai` message that requested it. assistant-ui instead nests the result
 *    inside the assistant message's `tool-call` part, so results are folded
 *    backwards onto the call they answer rather than emitted as messages.
 * 2. `content` is either a plain string or an array of typed blocks, and
 *    reasoning blocks have to survive as reasoning rather than be flattened
 *    into the visible answer.
 * 3. Some providers report reasoning outside `content` entirely. OpenRouter
 *    returns it in its own field, which `ChatOpenRouter` keeps in
 *    `additional_kwargs.reasoning`; it becomes a reasoning part here so both
 *    shapes render through the same component.
 */

type Json = Record<string, unknown>;

export type LangChainMessage = {
  type?: string;
  content?: unknown;
  id?: string | null;
  tool_calls?: Array<{
    id?: string | null;
    name?: string;
    args?: unknown;
  }> | null;
  tool_call_id?: string | null;
  status?: string | null;
  additional_kwargs?: Json | null;
};

type ToolCallPart = {
  type: 'tool-call';
  toolCallId: string;
  toolName: string;
  args: Json;
  result?: unknown;
  isError?: boolean;
};

/**
 * Synthetic tool name for a coalesced run of tool calls.
 *
 * The UI renders a run of tool calls as one collapsible block with any
 * artifacts hoisted out of it. Coalescing here -- where the whole run and all
 * its results are in hand -- lets a single component render that, instead of
 * reconstructing the grouping from individually-rendered parts downstream.
 */
export const TOOL_GROUP_NAME = '__wotbot_tool_group__';

/**
 * Synthetic tool name for a device-interaction summary turn.
 *
 * The agent emits a machine-readable summary of the WoT calls it made as an
 * ordinary assistant message. It is rendered as a summary card rather than as
 * prose, so it is recognised here and re-tagged as its own part; a turn that
 * looks like one but does not parse is dropped rather than shown raw.
 */
export const WOT_SUMMARY_NAME = '__wotbot_wot_summary__';

export type GroupedToolCall = {
  id: string;
  name: string;
  args: Json;
  result?: unknown;
  isError?: boolean;
};

type TextPart = { type: 'text'; text: string };
type ReasoningPart = { type: 'reasoning'; text: string };
type ContentPart = TextPart | ReasoningPart | ToolCallPart;

function isRecord(value: unknown): value is Json {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Tool results cross the wire as strings. The cards downstream expect the
 * decoded object (artifacts, stdout, wotInteractions), so decode when it is
 * JSON and pass the raw string through when it is not.
 */
function decodeToolResult(content: unknown): unknown {
  if (typeof content !== 'string') {
    return content;
  }
  const trimmed = content.trim();
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) {
    return content;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return content;
  }
}

/** Normalizes both string content and LangChain's typed content blocks. */
function toContentParts(content: unknown): ContentPart[] {
  if (typeof content === 'string') {
    return content ? [{ type: 'text', text: content }] : [];
  }
  if (!Array.isArray(content)) {
    return [];
  }

  const parts: ContentPart[] = [];
  for (const block of content) {
    if (typeof block === 'string') {
      if (block) parts.push({ type: 'text', text: block });
      continue;
    }
    if (!isRecord(block)) continue;

    const blockType = block.type;
    if (blockType === 'text' && typeof block.text === 'string') {
      if (block.text) parts.push({ type: 'text', text: block.text });
    } else if (
      (blockType === 'reasoning' || blockType === 'thinking') &&
      typeof (block.text ?? block.thinking) === 'string'
    ) {
      const text = (block.text ?? block.thinking) as string;
      if (text) parts.push({ type: 'reasoning', text });
    }
  }
  return parts;
}

/** Reasoning a provider reported beside `content` rather than inside it. */
function toDetachedReasoningParts(message: LangChainMessage): ContentPart[] {
  const reasoning = message.additional_kwargs?.reasoning;
  if (typeof reasoning !== 'string' || !reasoning.trim()) {
    return [];
  }
  return [{ type: 'reasoning', text: reasoning }];
}

function toGroupedCalls(message: LangChainMessage): GroupedToolCall[] {
  if (!Array.isArray(message.tool_calls)) {
    return [];
  }
  const calls: GroupedToolCall[] = [];
  for (const call of message.tool_calls) {
    if (!call?.id || !call.name) continue;
    calls.push({
      id: call.id,
      name: call.name,
      args: isRecord(call.args) ? call.args : {},
    });
  }
  return calls;
}

function makeGroupPart(calls: GroupedToolCall[]): ToolCallPart {
  return {
    type: 'tool-call',
    // Stable across streaming updates so the part keeps its identity.
    toolCallId: `group:${calls[0].id}`,
    toolName: TOOL_GROUP_NAME,
    args: { calls } as unknown as Json,
  };
}

export function toThreadMessages(
  messages: readonly LangChainMessage[] | undefined,
): ThreadMessageLike[] {
  if (!messages?.length) {
    return [];
  }

  const result: ThreadMessageLike[] = [];
  // Lets a `tool` message find the call it answers, however many assistant
  // messages back that was.
  const callsById = new Map<string, GroupedToolCall>();
  // The run currently being coalesced, so a following tool-only assistant
  // message extends it rather than starting a second collapsible block.
  let openGroup: GroupedToolCall[] | null = null;

  for (const message of messages) {
    const type = message.type;

    if (type === 'tool') {
      const call = message.tool_call_id
        ? callsById.get(message.tool_call_id)
        : undefined;
      if (call) {
        call.result = decodeToolResult(message.content);
        if (message.status === 'error') {
          call.isError = true;
        }
      }
      // A tool result does not break the run: the assistant's next tool-only
      // turn still belongs to the same block.
      continue;
    }

    if (type === 'human' || type === 'user') {
      openGroup = null;
      const content = toContentParts(message.content);
      if (content.length) {
        result.push({
          role: 'user',
          content: content as ThreadMessageLike['content'],
          ...(message.id ? { id: message.id } : {}),
        });
      }
      continue;
    }

    if (type === 'ai' || type === 'assistant' || type === 'AIMessageChunk') {
      const interactions = parseDeviceInteractionSummaryContent(
        message.content,
      );
      if (interactions.length > 0) {
        openGroup = null;
        result.push({
          role: 'assistant',
          content: [
            {
              type: 'tool-call',
              toolCallId: `wot:${message.id ?? result.length}`,
              toolName: WOT_SUMMARY_NAME,
              args: { interactions },
            },
          ] as ThreadMessageLike['content'],
          ...(message.id ? { id: message.id } : {}),
        });
        continue;
      }
      if (looksLikeDeviceInteractionSummaryContent(message.content)) {
        // Unparseable summary: hide it rather than render the raw payload.
        openGroup = null;
        continue;
      }

      const textParts = toContentParts(message.content);
      const reasoningParts = toDetachedReasoningParts(message);
      const calls = toGroupedCalls(message);
      for (const call of calls) {
        callsById.set(call.id, call);
      }

      // Tool-only turn: extend the open run instead of emitting a message.
      // Detached reasoning deliberately does not count as text here -- letting
      // it close the run would split one tool run into several cards. The cost
      // is that reasoning on a coalesced turn is not shown; the turn that ends
      // the run carries its own.
      if (!textParts.length && calls.length && openGroup) {
        openGroup.push(...calls);
        continue;
      }

      const parts: ContentPart[] = [...reasoningParts, ...textParts];
      if (calls.length) {
        // Text in the same turn closes the run: anything after it is a new
        // block, matching how the thread reads top to bottom.
        openGroup = textParts.length ? null : calls;
        parts.push(makeGroupPart(calls));
      } else {
        openGroup = null;
      }

      // An assistant turn with neither text nor a tool call would render as an
      // empty bubble; skip until it has something to show.
      if (parts.length) {
        result.push({
          role: 'assistant',
          content: parts as ThreadMessageLike['content'],
          ...(message.id ? { id: message.id } : {}),
        });
      }
      continue;
    }

    if (type === 'system') {
      // Job transcripts carry run-lifecycle lines as system messages; the chat
      // checkpoint never contains any, so emitting them here is safe.
      openGroup = null;
      const content = toContentParts(message.content);
      if (content.length) {
        result.push({
          role: 'system',
          content: content as ThreadMessageLike['content'],
          ...(message.id ? { id: message.id } : {}),
        });
      }
      continue;
    }

    // Unknown types are not rendered in the thread.
    openGroup = null;
  }

  return result;
}
