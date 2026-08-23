'use client';

import { MessagePartPrimitive, useAuiState } from '@assistant-ui/react';

/**
 * The model's reasoning, rendered inside the enclosing thought block.
 *
 * `thread-messages.ts` preserves `reasoning`/`thinking` blocks as their own
 * parts rather than flattening them into the answer, and `ChatOpenRouter` adds
 * the reasoning that OpenRouter reports beside `content`. assistant-ui defaults
 * `Reasoning` to `() => null`, so without this the text is parsed, carried to
 * the client and then dropped. Nothing renders when reasoning is off, since no
 * reasoning part is produced at all.
 *
 * This carries no chrome of its own: `ThoughtGroup` provides the one collapsible
 * for the whole turn, so a per-part toggle would nest a control inside a control.
 */
export function ReasoningPart() {
  // Selectors run inside useSyncExternalStore's getSnapshot, so this must
  // return a primitive: a fresh object every call reads as a changed snapshot
  // and spins React forever. Narrow rather than assume the part type, too --
  // a throw here tears down the React root.
  const hasText = useAuiState(
    (state) => state.part.type === 'reasoning' && state.part.text.length > 0,
  );

  // No text yet is the gap between the run starting and the first token.
  if (!hasText) {
    return null;
  }

  return (
    <MessagePartPrimitive.Text
      component="div"
      className="px-1 text-[0.76rem] leading-6 whitespace-pre-wrap break-words text-muted-foreground"
    />
  );
}
