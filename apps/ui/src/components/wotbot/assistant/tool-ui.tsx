'use client';

import type { ToolCallMessagePartProps } from '@assistant-ui/react';
import {
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Loader2,
  Wrench,
} from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';

import { GenericToolCallCard } from '@/components/wotbot/chat-tool-calls/generic-tool-call-card';
import {
  RunCodeArtifacts,
  RunCodeCard,
} from '@/components/wotbot/chat-tool-calls/run-code-card';
import {
  WebInterfaceArtifactView,
  WebInterfaceCard,
} from '@/components/wotbot/chat-tool-calls/web-interface-card';
import {
  enrichArtifactForPinning,
  normalizeWebInterfaceResult,
} from '@/components/wotbot/chat-tool-calls/web-interface-model';
import {
  createToolStatusCounts,
  formatToolCount,
  formatToolStatusSummary,
} from '@/components/wotbot/chat-tool-calls/grouped-tool-call-model';
import {
  hasErrorResult,
  normalizeRunCodeResult,
  type CatchAllToolCallRenderProps,
  type ToolCallStatus,
} from '@/components/wotbot/chat-tool-call-model';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import {
  TOOL_GROUP_NAME,
  WOT_SUMMARY_NAME,
  type GroupedToolCall,
} from '@/lib/thread-messages';
import { WotInteractionSummaryCard } from '@/components/wotbot/wot-summary/wot-interaction-summary-card';
import type { WotInteraction } from '@/lib/wot-interactions';

/**
 * Renders tool calls through the existing cards.
 *
 * assistant-ui's `tools.Override` is the counterpart of the CopilotKit
 * `defineToolCallRenderer({ name: '*' })` this replaces. The cards are
 * unchanged -- they already take `{args, name, result, status}`.
 *
 * A run of tool calls arrives coalesced into one synthetic part (see
 * `TOOL_GROUP_NAME`), which is what lets the compact cards sit inside a
 * collapsible while their artifacts -- plots, generated interfaces -- stay
 * hoisted above it, always visible.
 */

function toCardStatus(
  call: GroupedToolCall,
  groupStatus: ToolCallMessagePartProps['status'],
): ToolCallStatus {
  if (call.result !== undefined) {
    return 'complete';
  }
  return groupStatus?.type === 'running' ? 'executing' : 'inProgress';
}

function ToolActivityIcon({
  hasError,
  isComplete,
}: {
  hasError: boolean;
  isComplete: boolean;
}) {
  if (hasError) {
    return <CircleAlert className="size-3.5 text-destructive" />;
  }
  if (isComplete) {
    return (
      <CheckCircle2 className="size-3.5 text-emerald-600 dark:text-emerald-400" />
    );
  }
  return <Loader2 className="size-3.5 animate-spin text-primary" />;
}

function SingleToolCard(props: CatchAllToolCallRenderProps) {
  if (props.name === 'run_code') {
    return <RunCodeCard {...props} showArtifacts={false} />;
  }
  if (props.name === 'create_web_interface') {
    return <WebInterfaceCard {...props} showInterface={false} />;
  }
  return <GenericToolCallCard {...props} />;
}

function ToolCallGroup({
  calls,
  groupStatus,
}: {
  calls: GroupedToolCall[];
  groupStatus: ToolCallMessagePartProps['status'];
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  const { hasError, renderedArtifacts, renderedTools, statusCounts } =
    useMemo(() => {
      const renderedTools: ReactNode[] = [];
      const renderedArtifacts: ReactNode[] = [];
      const statusCounts = createToolStatusCounts();
      let hasError = false;

      for (const call of calls) {
        const props: CatchAllToolCallRenderProps = {
          args: call.args,
          name: call.name,
          result: call.result,
          status: toCardStatus(call, groupStatus),
        };
        statusCounts[props.status] += 1;
        const isComplete = props.status === 'complete';

        if (call.name === 'run_code') {
          const result = isComplete ? normalizeRunCodeResult(props.result) : {};
          hasError = hasError || Boolean(result.error);
          renderedTools.push(<SingleToolCard key={call.id} {...props} />);
          if (isComplete && result.artifacts?.length) {
            renderedArtifacts.push(
              <RunCodeArtifacts key={`${call.id}-artifacts`} result={result} />,
            );
          }
          continue;
        }

        if (call.name === 'create_web_interface') {
          const parsed = isComplete
            ? normalizeWebInterfaceResult(props.result)
            : {};
          hasError = hasError || Boolean(parsed.error);
          renderedTools.push(<SingleToolCard key={call.id} {...props} />);
          if (isComplete && parsed.artifact) {
            renderedArtifacts.push(
              <WebInterfaceArtifactView
                key={`${call.id}-interface`}
                artifact={enrichArtifactForPinning(parsed.artifact, props.args)}
              />,
            );
          }
          continue;
        }

        hasError = hasError || hasErrorResult(props.result);
        renderedTools.push(<SingleToolCard key={call.id} {...props} />);
      }

      return { hasError, renderedArtifacts, renderedTools, statusCounts };
    }, [calls, groupStatus]);

  const toolCount = calls.length;
  if (!toolCount) {
    return null;
  }

  const isComplete = statusCounts.complete === toolCount;
  const summary = formatToolStatusSummary({
    completeCount: statusCounts.complete,
    count: toolCount,
    executingCount: statusCounts.executing,
    inProgressCount: statusCounts.inProgress,
  });

  return (
    <div className="my-1 space-y-2">
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <div className="rounded-md border border-border/50 bg-muted/20">
          <CollapsibleTrigger asChild>
            <Button
              className="h-auto w-full justify-between gap-3 px-3 py-2 text-left hover:bg-muted/40"
              type="button"
              variant="ghost"
            >
              <span className="flex min-w-0 items-center gap-2.5">
                <ToolActivityIcon hasError={hasError} isComplete={isComplete} />
                <span className="min-w-0">
                  <span className="block truncate text-[0.76rem] font-medium text-foreground">
                    {formatToolCount(toolCount)}
                  </span>
                  <span className="block truncate text-[0.7rem] font-normal text-muted-foreground">
                    {summary}
                  </span>
                </span>
              </span>

              <span className="flex shrink-0 items-center gap-1.5 text-[0.68rem] font-medium text-muted-foreground">
                <Wrench className="size-3.5" />
                <span>{isExpanded ? 'Hide' : 'Details'}</span>
                <ChevronDown
                  className={cn(
                    'size-3 transition-transform',
                    isExpanded && 'rotate-180',
                  )}
                />
              </span>
            </Button>
          </CollapsibleTrigger>

          <CollapsibleContent className="data-closed:hidden">
            <div className="space-y-2 border-t border-border/45 p-2">
              {renderedTools}
            </div>
          </CollapsibleContent>
        </div>
      </Collapsible>

      {renderedArtifacts.length ? (
        <div className="space-y-2">{renderedArtifacts}</div>
      ) : null}
    </div>
  );
}

export function WotbotToolCall(props: ToolCallMessagePartProps) {
  if (props.toolName === WOT_SUMMARY_NAME) {
    const interactions =
      (props.args as { interactions?: WotInteraction[] })?.interactions ?? [];
    return <WotInteractionSummaryCard interactions={interactions} />;
  }

  if (props.toolName === TOOL_GROUP_NAME) {
    const calls = (props.args as { calls?: GroupedToolCall[] })?.calls ?? [];
    return <ToolCallGroup calls={calls} groupStatus={props.status} />;
  }

  // Any tool call that reached us ungrouped still renders on its own.
  return (
    <SingleToolCard
      args={props.args}
      name={props.toolName}
      result={props.result}
      status={props.status?.type === 'running' ? 'executing' : 'complete'}
    />
  );
}
