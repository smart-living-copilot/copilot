'use client';

import { memo, useState } from 'react';

import { ToolPayloadSection } from '@/components/wotbot/chat-tool-calls/tool-payload-section';
import {
  DetailsToggle,
  ToolCardHeader,
} from '@/components/wotbot/chat-tool-calls/tool-card-shell';
import { Collapsible, CollapsibleContent } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';

import {
  formatToolName,
  hasErrorResult,
  hasInspectableData,
  summarizeValue,
  TOOL_STATUS_DESCRIPTION,
  type CatchAllToolCallRenderProps,
} from '../chat-tool-call-model';

export const GenericToolCallCard = memo(function GenericToolCallCard({
  args,
  name,
  result,
  status,
}: CatchAllToolCallRenderProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const formattedName = formatToolName(name);
  const hasResult = hasInspectableData(result);
  const hasError = hasErrorResult(result);
  const hasArgs = hasInspectableData(args);
  const canExpand = hasArgs || hasResult;
  const isCompleted = status === 'complete';
  const summary = [
    summarizeValue('inputs', args),
    hasResult
      ? summarizeValue('result', result)
      : status === 'complete'
        ? 'result: none'
        : 'result: pending',
  ].join(' • ');

  return (
    <Collapsible
      className={cn(
        'wotbot-tool-call text-card-foreground',
        isExpanded && 'space-y-2',
      )}
      open={isExpanded}
      onOpenChange={setIsExpanded}
    >
      <ToolCardHeader
        action={
          canExpand ? (
            <DetailsToggle expanded={isExpanded} />
          ) : (
            <span className="text-[0.68rem] text-muted-foreground">
              {hasError ? 'Tool failed.' : TOOL_STATUS_DESCRIPTION[status]}
            </span>
          )
        }
        hasError={hasError}
        isCompleted={isCompleted}
        status={status}
        summary={!isCompleted ? summary : undefined}
        title={formattedName}
      />

      <CollapsibleContent className="data-closed:hidden">
        <div className="space-y-2 rounded-lg border border-border/45 bg-background/35 p-2.5">
          <ToolPayloadSection title="Inputs" value={args} />
          {hasResult ? (
            <ToolPayloadSection title="Result" value={result} />
          ) : status !== 'complete' ? (
            <div className="px-0.5 text-[0.72rem] text-muted-foreground">
              Waiting for the tool result to stream back.
            </div>
          ) : null}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
});
