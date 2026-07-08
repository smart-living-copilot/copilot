import { type ReactNode } from 'react';
import { CircleAlert, CheckCircle2, ChevronDown, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { CollapsibleTrigger } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';

import { type ToolCallStatus } from '../chat-tool-call-model';

function ToolStatusIcon({
  hasError = false,
  status,
}: {
  hasError?: boolean;
  status: ToolCallStatus;
}) {
  if (hasError) {
    return <CircleAlert className="size-3.5 text-destructive" />;
  }

  if (status === 'complete') {
    return (
      <CheckCircle2 className="size-3.5 text-emerald-600 dark:text-emerald-400" />
    );
  }

  return <Loader2 className="size-3.5 animate-spin text-primary" />;
}

export function ToolCardHeader({
  action,
  hasError = false,
  isCompleted,
  status,
  summary,
  title,
}: {
  action?: ReactNode;
  hasError?: boolean;
  isCompleted: boolean;
  status: ToolCallStatus;
  summary?: ReactNode;
  title: string;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 px-1 py-1">
      <div className="flex min-w-0 items-center gap-2.5">
        <ToolStatusIcon hasError={hasError} status={status} />

        <div className="min-w-0 space-y-0.5">
          <p
            className={cn(
              'truncate font-medium text-foreground',
              isCompleted ? 'text-[0.76rem]' : 'text-[0.82rem]',
            )}
          >
            {title}
          </p>

          {summary ? (
            <div className="truncate text-[0.7rem] text-muted-foreground">
              {summary}
            </div>
          ) : null}
        </div>
      </div>

      {action}
    </div>
  );
}

export function DetailsToggle({
  expanded,
  label = 'Details',
}: {
  expanded: boolean;
  label?: string;
}) {
  return (
    <CollapsibleTrigger asChild>
      <Button
        className="text-[0.66rem] font-medium text-muted-foreground hover:text-foreground"
        size="xs"
        type="button"
        variant="ghost"
      >
        <span>{expanded ? `Hide ${label.toLowerCase()}` : label}</span>
        <ChevronDown
          className={cn(
            'size-3 transition-transform',
            expanded && 'rotate-180',
          )}
        />
      </Button>
    </CollapsibleTrigger>
  );
}
