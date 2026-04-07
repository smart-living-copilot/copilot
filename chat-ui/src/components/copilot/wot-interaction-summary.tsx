'use client';

import { memo, useMemo, useState, type ComponentProps } from 'react';
import Link from 'next/link';
import { CopilotChatMessageView } from '@copilotkit/react-core/v2';
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  ChevronDown,
  CirclePlay,
} from 'lucide-react';
import type { WotInteraction } from '@/lib/wot-interactions';
import { getLastTurnWotInteractions } from '@/lib/wot-interactions';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { formatToolData, hasInspectableData } from './chat-tool-call-model';

const TYPE_LABELS: Record<string, { label: string; icon: typeof CirclePlay }> =
  {
    invoke_action: { label: 'Action', icon: CirclePlay },
    read_property: { label: 'Read', icon: ArrowDownToLine },
    write_property: { label: 'Write', icon: ArrowUpFromLine },
    observe_property: { label: 'Observe', icon: ArrowDownToLine },
    subscribe_event: { label: 'Subscribe', icon: CirclePlay },
  };

function lastThingSegment(thingId: string) {
  const parts = thingId.split(/[/:]/);
  return parts[parts.length - 1] || thingId;
}

function getThingHref(thingId: string) {
  return `/things/${encodeURIComponent(thingId)}`;
}

function formatSummaryDescription(interactions: WotInteraction[]) {
  const thingCount = new Set(
    interactions.map((interaction) => interaction.thingId),
  ).size;
  const failCount = interactions.filter((i) => !i.ok).length;
  const parts = [
    `${interactions.length} interaction${interactions.length === 1 ? '' : 's'}`,
    `${thingCount} thing${thingCount === 1 ? '' : 's'}`,
  ];
  if (failCount) {
    parts.push(`${failCount} failed`);
  }
  return parts.join(' · ');
}

function getInteractionPrimaryDetail(interaction: WotInteraction) {
  if (interaction.type === 'write_property') {
    return {
      label: 'Value',
      value: interaction.value,
    };
  }

  if (
    interaction.type === 'invoke_action' ||
    interaction.type === 'subscribe_event'
  ) {
    return {
      label: 'Input',
      value: interaction.input,
    };
  }

  return null;
}

function hasInteractionDetails(interaction: WotInteraction) {
  const primaryDetail = getInteractionPrimaryDetail(interaction);

  return Boolean(
    (primaryDetail && hasInspectableData(primaryDetail.value)) ||
    hasInspectableData(interaction.uriVariables),
  );
}

const WotInteractionRow = memo(function WotInteractionRow({
  interaction,
}: {
  interaction: WotInteraction;
}) {
  const [open, setOpen] = useState(false);
  const meta = TYPE_LABELS[interaction.type];
  const Icon = meta?.icon ?? CirclePlay;
  const primaryDetail = getInteractionPrimaryDetail(interaction);
  const showPrimaryDetail = Boolean(
    primaryDetail && hasInspectableData(primaryDetail.value),
  );
  const showUriVariables = hasInspectableData(interaction.uriVariables);
  const hasDetails = hasInteractionDetails(interaction);

  return (
    <Collapsible
      className="rounded-md border border-border/50 bg-background/80"
      open={open}
      onOpenChange={setOpen}
    >
      <div className="flex items-center justify-between gap-2 px-2.5 py-1.5">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="size-3 shrink-0 text-muted-foreground" />
          <span className="text-[0.72rem] font-medium text-foreground">
            {meta?.label ?? interaction.type}
          </span>
          <Link
            className="truncate font-mono text-[0.66rem] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            href={getThingHref(interaction.thingId)}
            prefetch={false}
            rel="noreferrer"
            target="_blank"
            title={interaction.thingId}
          >
            {lastThingSegment(interaction.thingId)}
          </Link>
          <span className="truncate text-[0.66rem] text-muted-foreground">
            {interaction.affordanceName || '—'}
          </span>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          {hasDetails ? (
            <CollapsibleTrigger asChild>
              <Button
                className="h-auto px-0 text-[0.66rem] font-medium text-muted-foreground hover:text-foreground"
                size="xs"
                type="button"
                variant="ghost"
              >
                <span>{open ? 'Hide inputs' : 'Inputs'}</span>
                <ChevronDown
                  className={cn(
                    'size-3 transition-transform',
                    open && 'rotate-180',
                  )}
                />
              </Button>
            </CollapsibleTrigger>
          ) : null}

          <span
            className={cn(
              'text-[0.66rem]',
              interaction.ok ? 'text-muted-foreground' : 'text-destructive',
            )}
          >
            {interaction.ok ? 'OK' : 'Failed'}
          </span>
        </div>
      </div>

      {hasDetails ? (
        <CollapsibleContent className="data-closed:hidden">
          <div className="space-y-2 border-t border-border/45 px-2.5 py-2">
            {showPrimaryDetail && primaryDetail ? (
              <div className="space-y-1">
                <p className="text-[0.62rem] font-medium tracking-[0.12em] text-muted-foreground uppercase">
                  {primaryDetail.label}
                </p>
                <pre className="overflow-auto rounded-md border border-border/45 bg-background px-2 py-1.5 text-[0.68rem] leading-5 whitespace-pre-wrap text-foreground">
                  {formatToolData(primaryDetail.value)}
                </pre>
              </div>
            ) : null}

            {showUriVariables ? (
              <div className="space-y-1">
                <p className="text-[0.62rem] font-medium tracking-[0.12em] text-muted-foreground uppercase">
                  URI Variables
                </p>
                <pre className="overflow-auto rounded-md border border-border/45 bg-background px-2 py-1.5 text-[0.68rem] leading-5 whitespace-pre-wrap text-foreground">
                  {formatToolData(interaction.uriVariables)}
                </pre>
              </div>
            ) : null}
          </div>
        </CollapsibleContent>
      ) : null}
    </Collapsible>
  );
});

const WotInteractionSummaryCard = memo(function WotInteractionSummaryCard({
  interactions,
}: {
  interactions: WotInteraction[];
}) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible
      className="smart-living-tool-call space-y-2"
      open={open}
      onOpenChange={setOpen}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 px-1 py-1">
        <div className="min-w-0 space-y-0.5">
          <p className="truncate text-[0.76rem] font-medium text-foreground">
            Device Interactions
          </p>
          <div className="truncate text-[0.7rem] text-muted-foreground">
            {formatSummaryDescription(interactions)}
          </div>
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
              className={cn(
                'size-3 transition-transform',
                open && 'rotate-180',
              )}
            />
          </Button>
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent className="data-closed:hidden">
        <div className="space-y-1.5 rounded-lg border border-border/45 bg-background/35 p-2.5">
          {interactions.map((interaction, index) => {
            return (
              <WotInteractionRow
                interaction={interaction}
                key={`${interaction.type}:${interaction.thingId}:${interaction.affordanceName}:${index}`}
              />
            );
          })}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
});

function MessageViewWithWotSummaryImpl({
  className,
  isRunning = false,
  messages = [],
  ...props
}: ComponentProps<typeof CopilotChatMessageView>) {
  const interactions = useMemo(() => {
    if (isRunning) {
      return [];
    }

    return getLastTurnWotInteractions(messages);
  }, [isRunning, messages]);

  return (
    <div className={cn('flex flex-1 flex-col gap-3 pt-2', className)}>
      <CopilotChatMessageView
        {...props}
        isRunning={isRunning}
        messages={messages}
      />
      {interactions.length ? (
        <WotInteractionSummaryCard interactions={interactions} />
      ) : null}
    </div>
  );
}

export const MessageViewWithWotSummary = Object.assign(
  MessageViewWithWotSummaryImpl,
  {
    Cursor: CopilotChatMessageView.Cursor,
  },
);
