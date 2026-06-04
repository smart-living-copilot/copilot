'use client';

import { useMemo, useState, type ComponentProps, type ReactNode } from 'react';
import {
  CopilotChatAssistantMessage,
  useCopilotKit,
  useRenderToolCall,
} from '@copilotkit/react-core/v2';
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
} from '@/components/copilot/chat-tool-calls/run-code-card';
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
  type CatchAllToolCallRenderProps,
  type ToolCallStatus,
} from '../chat-tool-call-model';

type AssistantMessageProps = ComponentProps<typeof CopilotChatAssistantMessage>;
type AssistantMessage = AssistantMessageProps['message'];
type Message = NonNullable<AssistantMessageProps['messages']>[number];
type ToolCall = NonNullable<AssistantMessage['toolCalls']>[number];
type ToolMessage = Extract<Message, { role: 'tool' }>;

export function isToolOnlyAssistantMessage(
  message: Message,
): message is AssistantMessage {
  return (
    message.role === 'assistant' &&
    (message.toolCalls?.length ?? 0) > 0 &&
    !(message.content ?? '').trim()
  );
}

export function isFirstToolOnlyMessageInGroup({
  message,
  messages,
}: {
  message: AssistantMessage;
  messages: Message[];
}) {
  if (!isToolOnlyAssistantMessage(message)) {
    return true;
  }

  const messageIndex = messages.findIndex(
    (candidate) => candidate.id === message.id,
  );
  if (messageIndex <= 0) {
    return true;
  }

  for (let index = messageIndex - 1; index >= 0; index -= 1) {
    const previous = messages[index];
    if (!previous || previous.role === 'tool') {
      continue;
    }

    return !isToolOnlyAssistantMessage(previous);
  }

  return true;
}

function getGroupedToolCalls({
  message,
  messages,
}: {
  message: AssistantMessage;
  messages: Message[];
}) {
  if (
    (message.toolCalls?.length ?? 0) === 0 ||
    (message.content ?? '').trim()
  ) {
    return message.toolCalls ?? [];
  }

  const groupedToolCalls: ToolCall[] = [];
  const messageIndex = messages.findIndex(
    (candidate) => candidate.id === message.id,
  );
  if (messageIndex < 0) {
    return message.toolCalls ?? [];
  }

  for (let index = messageIndex; index < messages.length; index += 1) {
    const current = messages[index];
    if (!current) {
      continue;
    }
    if (current.role === 'tool') {
      continue;
    }
    if (!isToolOnlyAssistantMessage(current)) {
      break;
    }

    groupedToolCalls.push(...(current.toolCalls ?? []));
  }

  return groupedToolCalls;
}

function parseToolArgs(rawArgs: string) {
  try {
    const parsed = JSON.parse(rawArgs);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed
      : {};
  } catch {
    return {};
  }
}

function getToolStatus({
  executingToolCallIds,
  toolCall,
  toolMessage,
}: {
  executingToolCallIds: ReadonlySet<string>;
  toolCall: ToolCall;
  toolMessage?: ToolMessage;
}): ToolCallStatus {
  if (toolMessage) {
    return 'complete';
  }

  return executingToolCallIds.has(toolCall.id) ? 'executing' : 'inProgress';
}

function buildToolCallProps({
  executingToolCallIds,
  toolCall,
  toolMessage,
}: {
  executingToolCallIds: ReadonlySet<string>;
  toolCall: ToolCall;
  toolMessage?: ToolMessage;
}): CatchAllToolCallRenderProps {
  return {
    args: parseToolArgs(toolCall.function.arguments),
    name: toolCall.function.name,
    result: toolMessage?.content,
    status: getToolStatus({ executingToolCallIds, toolCall, toolMessage }),
  };
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

function formatToolCount(count: number) {
  return `${count} tool${count === 1 ? '' : 's'} called`;
}

function formatToolStatusSummary({
  completeCount,
  count,
  executingCount,
  inProgressCount,
}: {
  completeCount: number;
  count: number;
  executingCount: number;
  inProgressCount: number;
}) {
  if (completeCount === count) {
    return 'Finished';
  }

  const parts = [];
  if (executingCount) {
    parts.push(`${executingCount} running`);
  }
  if (inProgressCount) {
    parts.push(`${inProgressCount} preparing`);
  }
  if (completeCount) {
    parts.push(`${completeCount} complete`);
  }

  return parts.join(' • ') || 'Working';
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
      const statusCounts = {
        complete: 0,
        executing: 0,
        inProgress: 0,
      } satisfies Record<ToolCallStatus, number>;
      let hasError = false;

      for (const toolCall of toolCalls) {
        const toolMessage = messages.find(
          (candidate): candidate is ToolMessage =>
            candidate.role === 'tool' && candidate.toolCallId === toolCall.id,
        );
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
