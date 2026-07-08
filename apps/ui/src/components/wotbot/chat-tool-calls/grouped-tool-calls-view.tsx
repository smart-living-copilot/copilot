'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { type AssistantMessage, type Message } from '@ag-ui/core';
import { useCopilotKit, useRenderToolCall } from '@copilotkit/react-core/v2';
import {
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Loader2,
  Wrench,
} from 'lucide-react';

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
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';

import {
  hasErrorResult,
  normalizeRunCodeResult,
} from '../chat-tool-call-model';
import {
  buildToolCallProps,
  createToolStatusCounts,
  formatToolCount,
  formatToolStatusSummary,
  getGroupedToolCalls,
  getToolMessageForCall,
} from './grouped-tool-call-model';

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

export function GroupedToolCallsView({
  message,
  messages = [],
}: {
  message: AssistantMessage;
  messages?: Message[];
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const { executingToolCallIds } = useCopilotKit();
  const renderToolCall = useRenderToolCall();
  const toolCalls = useMemo(
    () => getGroupedToolCalls({ message, messages }),
    [message, messages],
  );

  const { hasError, renderedArtifacts, renderedTools, statusCounts } =
    useMemo(() => {
      const renderedTools: ReactNode[] = [];
      const renderedArtifacts: ReactNode[] = [];
      const statusCounts = createToolStatusCounts();
      let hasError = false;

      for (const toolCall of toolCalls) {
        const toolMessage = getToolMessageForCall({ messages, toolCall });
        const props = buildToolCallProps({
          executingToolCallIds,
          toolCall,
          toolMessage,
        });
        statusCounts[props.status] += 1;

        if (toolCall.function.name === 'run_code') {
          const result =
            props.status === 'complete'
              ? normalizeRunCodeResult(props.result)
              : {};
          hasError = hasError || Boolean(result.error);
          renderedTools.push(
            <RunCodeCard key={toolCall.id} {...props} showArtifacts={false} />,
          );

          if (props.status === 'complete' && result.artifacts?.length) {
            renderedArtifacts.push(
              <RunCodeArtifacts
                key={`${toolCall.id}-artifacts`}
                result={result}
              />,
            );
          }
          continue;
        }

        if (toolCall.function.name === 'create_web_interface') {
          const parsed =
            props.status === 'complete'
              ? normalizeWebInterfaceResult(props.result)
              : {};
          hasError = hasError || Boolean(parsed.error);
          renderedTools.push(
            <WebInterfaceCard
              key={toolCall.id}
              {...props}
              showInterface={false}
            />,
          );

          if (props.status === 'complete' && parsed.artifact) {
            renderedArtifacts.push(
              <WebInterfaceArtifactView
                key={`${toolCall.id}-interface`}
                artifact={enrichArtifactForPinning(parsed.artifact, props.args)}
              />,
            );
          }
          continue;
        }

        hasError = hasError || hasErrorResult(props.result);
        renderedTools.push(renderToolCall({ toolCall, toolMessage }) ?? null);
      }

      return {
        hasError,
        renderedArtifacts,
        renderedTools,
        statusCounts,
      };
    }, [executingToolCallIds, messages, renderToolCall, toolCalls]);

  const toolCount = toolCalls.length;
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
