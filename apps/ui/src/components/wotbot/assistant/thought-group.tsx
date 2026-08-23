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
import { Brain, ChevronDown, CircleAlert, Loader2, Wrench } from 'lucide-react';

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

function formatSummary(toolCount: number, isRunning: boolean): string {
  if (toolCount === 0) {
    return isRunning ? 'Thinking' : 'Thought process';
  }
  const tools = `${toolCount} tool${toolCount === 1 ? '' : 's'}`;
  return isRunning ? `Working with ${tools}` : `Thought and used ${tools}`;
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

  const label = formatSummary(toolIds.size, isRunning);

  return (
    <ThoughtGroupContext.Provider value={report}>
      <div className="my-1">
        <Collapsible open={isExpanded} onOpenChange={handleExpandedChange}>
          <div className="rounded-md border border-border/50 bg-muted/20">
            <CollapsibleTrigger asChild>
              <Button
                className="h-auto w-full justify-between gap-3 px-3 py-2 text-left hover:bg-muted/40"
                type="button"
                variant="ghost"
              >
                <span className="flex min-w-0 items-center gap-2.5">
                  {hasError ? (
                    <CircleAlert className="size-3.5 shrink-0 text-destructive" />
                  ) : isRunning ? (
                    <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
                  ) : (
                    <Brain className="size-3.5 shrink-0 text-muted-foreground" />
                  )}
                  <span className="min-w-0 truncate text-[0.76rem] font-medium text-foreground">
                    {isRunning ? <ShimmerLabel>{label}</ShimmerLabel> : label}
                  </span>
                </span>

                <span className="flex shrink-0 items-center gap-1.5 text-[0.68rem] font-medium text-muted-foreground">
                  {toolIds.size > 0 ? <Wrench className="size-3.5" /> : null}
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

            {/* forceMount: the parts inside report themselves upward, and a
                collapsed block that unmounted them would title itself "Thought
                process" until first opened, then change once it could count. */}
            <CollapsibleContent forceMount className="data-[state=closed]:hidden">
              <div className="space-y-2 border-t border-border/45 p-2">
                {children}
              </div>
            </CollapsibleContent>
          </div>
        </Collapsible>
      </div>
    </ThoughtGroupContext.Provider>
  );
}

/** Consecutive runs inside the block; the shell owns the chrome. */
export function ThoughtSubGroup({ children }: { children: ReactNode }) {
  return <div className="space-y-2">{children}</div>;
}
