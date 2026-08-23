'use client';

import { useState } from 'react';
import { useAuiState } from '@assistant-ui/react';
import { MarkdownTextPrimitive } from '@assistant-ui/react-markdown';
import { ChevronDown } from 'lucide-react';

import { markdownRemarkPlugins } from '@/components/wotbot/assistant/markdown';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { ShimmerLabel } from '@/lib/surfaces';
import { cn } from '@/lib/utils';

/**
 * One reasoning step inside the thought block.
 *
 * `thread-messages.ts` preserves `reasoning`/`thinking` blocks as their own
 * parts rather than flattening them into the answer, and `ChatOpenRouter` adds
 * the reasoning that OpenRouter reports beside `content`. assistant-ui defaults
 * `Reasoning` to `() => null`, so without this the text is parsed, carried to
 * the client and then dropped.
 *
 * A step collapses on its own: a tool loop produces several, each a thousand
 * characters or more, and a block that dumped them all at once would bury the
 * tool cards between them. The header matches the tool and device-interaction
 * cards so every row inside the block reads the same way.
 */

/** The model writes a bolded title on its first line; use it as the summary. */
function toStepSummary(text: string): string {
  const firstLine = text.trim().split('\n', 1)[0] ?? '';
  const heading = firstLine.replace(/^#+\s*/, '').replace(/\*\*/g, '').trim();
  return heading.length > 90 ? `${heading.slice(0, 89)}…` : heading;
}

export function ReasoningPart() {
  const [open, setOpen] = useState(false);

  // These selectors run inside useSyncExternalStore's getSnapshot, so each must
  // return a primitive: a fresh object every call reads as a changed snapshot
  // and spins React forever. Narrow rather than assume the part type, too --
  // a throw here tears down the React root.
  const text = useAuiState((state) =>
    state.part.type === 'reasoning' ? state.part.text : '',
  );
  const isRunning = useAuiState(
    (state) =>
      state.part.type === 'reasoning' && state.part.status.type === 'running',
  );

  // No text yet is the gap between the run starting and the first token.
  if (!text) {
    return null;
  }

  const summary = toStepSummary(text);

  return (
    <Collapsible className="space-y-2" open={open} onOpenChange={setOpen}>
      <div className="flex flex-wrap items-center justify-between gap-2 px-1 py-1">
        <div className="min-w-0 space-y-0.5">
          <p className="truncate text-[0.76rem] font-medium text-foreground">
            {isRunning ? <ShimmerLabel>Thinking</ShimmerLabel> : 'Thought'}
          </p>
          {summary ? (
            <div className="truncate text-[0.7rem] text-muted-foreground">
              {summary}
            </div>
          ) : null}
        </div>

        <CollapsibleTrigger asChild>
          <Button
            className="text-[0.66rem] font-medium text-muted-foreground hover:text-foreground"
            size="xs"
            type="button"
            variant="ghost"
          >
            <span>{open ? 'Hide details' : 'Details'}</span>
            <ChevronDown
              className={cn('size-3 transition-transform', open && 'rotate-180')}
            />
          </Button>
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent>
        <MarkdownTextPrimitive
          remarkPlugins={markdownRemarkPlugins}
          className={cn(
            'wotbot-markdown prose prose-sm max-w-none break-words px-1',
            'text-[0.76rem] text-muted-foreground',
            '[&_*]:text-muted-foreground [&_p]:my-1.5 [&_ul]:my-1.5 [&_ol]:my-1.5',
            '[&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-muted [&_pre]:p-2',
          )}
        />
      </CollapsibleContent>
    </Collapsible>
  );
}
