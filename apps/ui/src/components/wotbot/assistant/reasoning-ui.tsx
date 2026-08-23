'use client';

import { useState } from 'react';
import { MessagePartPrimitive, useAuiState } from '@assistant-ui/react';
import { Brain, ChevronDown } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { ShimmerLabel } from '@/lib/surfaces';
import { cn } from '@/lib/utils';

/**
 * Renders the model's reasoning as a collapsed block.
 *
 * `thread-messages.ts` deliberately preserves `reasoning`/`thinking` blocks as
 * their own parts rather than flattening them into the answer, but assistant-ui
 * defaults `Reasoning` to `() => null`, so until this component was registered
 * the text was parsed, carried to the client and then silently dropped. That
 * only matters when REASONING_EFFORT_ENABLED is on -- with it off, no reasoning
 * part is ever produced and nothing here renders.
 *
 * Collapsed by default in both states: reasoning is supporting material, and a
 * block that auto-expands while streaming and then snaps shut moves the answer
 * around under the reader.
 */
export function ReasoningPart() {
  const [isExpanded, setIsExpanded] = useState(false);

  // These selectors run inside useSyncExternalStore's getSnapshot, so each must
  // return a primitive: a fresh object every call reads as a changed snapshot
  // and spins React forever. Narrow rather than assume the part type, too --
  // a throw here tears down the React root.
  const hasText = useAuiState(
    (auiState) => auiState.part.type === 'reasoning' && auiState.part.text.length > 0,
  );
  const isRunning = useAuiState(
    (auiState) =>
      auiState.part.type === 'reasoning' && auiState.part.status.type === 'running',
  );

  // No text yet is the gap between the run starting and the first token;
  // rendering the shell there would flash an empty box before every answer.
  if (!hasText) {
    return null;
  }

  const label = isRunning ? 'Thinking' : 'Thought process';

  return (
    <div className="my-1">
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <div className="rounded-md border border-border/50 bg-muted/20">
          <CollapsibleTrigger asChild>
            <Button
              className="h-auto w-full justify-between gap-3 px-3 py-2 text-left hover:bg-muted/40"
              type="button"
              variant="ghost"
            >
              <span className="flex min-w-0 items-center gap-2.5">
                <Brain
                  className={cn(
                    'size-3.5 shrink-0',
                    isRunning ? 'text-primary' : 'text-muted-foreground',
                  )}
                />
                <span className="min-w-0 truncate text-[0.76rem] font-medium text-foreground">
                  {isRunning ? (
                    <ShimmerLabel>{label}</ShimmerLabel>
                  ) : (
                    label
                  )}
                </span>
              </span>

              <span className="flex shrink-0 items-center gap-1.5 text-[0.68rem] font-medium text-muted-foreground">
                <span>{isExpanded ? 'Hide' : 'Show'}</span>
                <ChevronDown
                  className={cn(
                    'size-3 transition-transform',
                    isExpanded && 'rotate-180',
                  )}
                />
              </span>
            </Button>
          </CollapsibleTrigger>

          <CollapsibleContent>
            <div className="border-t border-border/50 px-3 py-2">
              <MessagePartPrimitive.Text
                component="div"
                className="text-[0.76rem] leading-6 whitespace-pre-wrap break-words text-muted-foreground"
              />
            </div>
          </CollapsibleContent>
        </div>
      </Collapsible>
    </div>
  );
}
