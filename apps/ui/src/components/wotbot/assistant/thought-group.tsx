'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { ChevronDown, CircleAlert, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { ShimmerLabel } from '@/lib/surfaces';
import { cn } from '@/lib/utils';

/**
 * The single collapsed block holding a turn's reasoning and tool calls.
 *
 * Membership is decided structurally by `wotbotGroupBy`; this component only
 * renders the shell. It cannot inspect its own children, so the two things it
 * needs to know about them -- how many tool calls there are, and whether any
 * failed -- are reported upwards through context by the parts themselves.
 */

type ThoughtGroupReport = {
  reportError: () => void;
  reportTool: (toolCallId: string) => void;
};

const ThoughtGroupContext = createContext<ThoughtGroupReport | null>(null);

/** Lets a tool card inside the block tell the shell it exists, and if it failed. */
export function useThoughtGroupReport(): ThoughtGroupReport | null {
  return useContext(ThoughtGroupContext);
}

/** Registers a tool call with the enclosing block for the duration it is shown. */
export function useReportToolCall(toolCallId: string, hasError: boolean) {
  const report = useThoughtGroupReport();

  useEffect(() => {
    report?.reportTool(toolCallId);
  }, [report, toolCallId]);

  useEffect(() => {
    if (hasError) {
      report?.reportError();
    }
  }, [hasError, report]);
}

/** Mirrors the device-interaction card: a fixed title over a counts line. */
function formatDetail(toolCount: number, hasError: boolean): string {
  const parts = [`${toolCount} tool${toolCount === 1 ? '' : 's'}`];
  if (hasError) {
    parts.push('1 failed');
  }
  return parts.join(' · ');
}

export function ThoughtGroup({
  children,
  isRunning,
}: {
  children: ReactNode;
  isRunning: boolean;
}) {
  const [isManuallyExpanded, setIsManuallyExpanded] = useState(false);
  const [shouldAutoExpandError, setShouldAutoExpandError] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [toolIds, setToolIds] = useState<ReadonlySet<string>>(new Set());

  const report = useMemo<ThoughtGroupReport>(
    () => ({
      reportError: () => setHasError(true),
      reportTool: (toolCallId: string) =>
        setToolIds((current) =>
          current.has(toolCallId) ? current : new Set(current).add(toolCallId),
        ),
    }),
    [],
  );

  // A failure opens the block as soon as it arrives. Once the user explicitly
  // collapses it, keep respecting that choice instead of forcing it back open.
  const isExpanded = isManuallyExpanded || (hasError && shouldAutoExpandError);
  const handleExpandedChange = useCallback(
    (open: boolean) => {
      setIsManuallyExpanded(open);
      if (!open) {
        setShouldAutoExpandError(false);
      }
    },
    [],
  );

  const label = isRunning ? 'Thinking' : 'Thought process';
  const detail = formatDetail(toolIds.size, hasError);

  return (
    <ThoughtGroupContext.Provider value={report}>
      <Collapsible
        className="wotbot-tool-call my-1 space-y-2"
        open={isExpanded}
        onOpenChange={handleExpandedChange}
      >
        {/* Same header shape as the tool and device-interaction cards, so the
            chat reads as one family of blocks rather than three. */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-1 py-1">
          <div className="flex min-w-0 items-center gap-2">
            {/* No resting icon: the block leads with text like the device-
                interaction card. Only a failure or an active run earns one. */}
            {hasError ? (
              <CircleAlert className="size-3.5 shrink-0 text-destructive" />
            ) : isRunning ? (
              <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
            ) : null}
            <div className="min-w-0 space-y-0.5">
              <p className="truncate text-[0.76rem] font-medium text-foreground">
                {isRunning ? <ShimmerLabel>{label}</ShimmerLabel> : label}
              </p>
              {toolIds.size > 0 ? (
                <div className="truncate text-[0.7rem] text-muted-foreground">
                  {detail}
                </div>
              ) : null}
            </div>
          </div>

          <CollapsibleTrigger asChild>
            <Button
              className="text-[0.66rem] font-medium text-muted-foreground hover:text-foreground"
              size="xs"
              type="button"
              variant="ghost"
            >
              <span>{isExpanded ? 'Hide details' : 'Details'}</span>
              <ChevronDown
                className={cn(
                  'size-3 transition-transform',
                  isExpanded && 'rotate-180',
                )}
              />
            </Button>
          </CollapsibleTrigger>
        </div>

        {/* forceMount: the parts inside report themselves upward, and a
            collapsed block that unmounted them would title itself "Thought
            process" until first opened, then change once it could count. */}
        <CollapsibleContent forceMount className="data-[state=closed]:hidden">
          <div className="space-y-1 border-l border-border/60 pl-3">
            {children}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </ThoughtGroupContext.Provider>
  );
}

/** Consecutive runs inside the block; the shell owns the chrome. */
export function ThoughtSubGroup({ children }: { children: ReactNode }) {
  return <div className="space-y-2">{children}</div>;
}
