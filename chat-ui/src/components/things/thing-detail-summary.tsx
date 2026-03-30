'use client';

import Link from 'next/link';
import { type ReactNode } from 'react';
import { Loader2, Pencil, Trash2 } from 'lucide-react';

import { type ThingRecord } from '@/lib/things-api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';

import {
  type ActionDef,
  formatDateTime,
  formatIndexerLabel,
  type EventDef,
  type PropertyDef,
  type ThingIndexStatus,
} from './thing-detail-model';
import { ThingIndexStatusBadge } from './thing-index-status-badge';

function DetailStat({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border/70 bg-muted/20 p-4">
      <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </p>
      <div
        className={`mt-2 text-sm font-medium text-foreground ${mono ? 'break-all font-mono text-xs leading-6' : ''}`}
      >
        {value}
      </div>
    </div>
  );
}

function SemanticBadgeList({
  label,
  items,
  emptyText,
}: {
  label: string;
  items?: string[];
  emptyText: string;
}) {
  const values = (items ?? []).filter((item) => item.trim().length > 0);

  return (
    <div className="space-y-2">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      {values.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {values.map((item) => (
            <Badge
              key={`${label}:${item}`}
              variant="outline"
              className="font-normal"
            >
              {item}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      )}
    </div>
  );
}

export function ThingSummaryCard({
  thing,
  title,
  description,
  securityStr,
  properties,
  actions,
  events,
  indexStatus,
  isDeleting,
  onDelete,
}: {
  thing: ThingRecord;
  title: string;
  description: string;
  securityStr: string;
  properties: PropertyDef[];
  actions: ActionDef[];
  events: EventDef[];
  indexStatus: ThingIndexStatus | null;
  isDeleting: boolean;
  onDelete: () => Promise<void> | void;
}) {
  return (
    <Card className="border border-border/70 shadow-sm shadow-black/5">
      <CardHeader className="gap-4 border-b border-border/70">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                Thing detail
              </p>
              <h1 className="text-3xl font-semibold tracking-tight text-foreground md:text-4xl">
                {title}
              </h1>
            </div>
            <p className="max-w-3xl text-sm leading-7 text-muted-foreground">
              {description}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <ThingIndexStatusBadge status={indexStatus} />
              <Badge variant="outline" className="font-normal">
                Security {securityStr}
              </Badge>
              <Badge variant="outline" className="font-normal">
                {properties.length} propert
                {properties.length === 1 ? 'y' : 'ies'}
              </Badge>
              <Badge variant="outline" className="font-normal">
                {actions.length} action{actions.length === 1 ? '' : 's'}
              </Badge>
              <Badge variant="outline" className="font-normal">
                {events.length} event{events.length === 1 ? '' : 's'}
              </Badge>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button asChild variant="outline">
              <Link href={`/things/${encodeURIComponent(thing.id)}/edit`}>
                <Pencil className="h-4 w-4" />
                Edit JSON
              </Link>
            </Button>
            <Button
              variant="destructive"
              onClick={() => void onDelete()}
              disabled={isDeleting}
            >
              {isDeleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              {isDeleting ? 'Removing...' : 'Remove Thing'}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 pt-4 md:grid-cols-2 xl:grid-cols-3">
        <DetailStat label="Thing ID" value={thing.id} mono />
        <DetailStat
          label="Indexed At"
          value={formatDateTime(indexStatus?.indexed_at)}
        />
        <DetailStat
          label="Summary Model"
          value={indexStatus?.summary_model ?? '-'}
        />
      </CardContent>
    </Card>
  );
}

export function ThingSemanticSection({
  indexStatus,
  semanticSummary,
  semanticIndexed,
}: {
  indexStatus: ThingIndexStatus | null;
  semanticSummary?: string;
  semanticIndexed: boolean;
}) {
  return (
    <Card className="border border-border/70 shadow-sm shadow-black/5">
      <CardHeader>
        <CardTitle className="text-2xl">Semantic summary</CardTitle>
        <CardDescription>
          Latest summary and extracted terms from the semantic indexer.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap items-center gap-2">
          <ThingIndexStatusBadge status={indexStatus} />
          {semanticIndexed && indexStatus?.summary_source ? (
            <Badge variant="outline" className="font-normal">
              Source {formatIndexerLabel(indexStatus.summary_source)}
            </Badge>
          ) : null}
          {semanticIndexed && indexStatus?.summary_model ? (
            <Badge variant="outline" className="font-normal">
              Model {indexStatus.summary_model}
            </Badge>
          ) : null}
          {semanticIndexed && indexStatus?.td_hash_match === false ? (
            <Badge
              variant="outline"
              className="border-yellow-500/60 font-normal text-yellow-700"
            >
              Stale snapshot
            </Badge>
          ) : null}
        </div>

        <div className="space-y-3">
          <div className="space-y-1">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Indexed at
            </p>
            <p className="text-sm text-muted-foreground">
              {formatDateTime(indexStatus?.indexed_at)}
            </p>
          </div>

          {indexStatus === null ? (
            <div className="rounded-lg border px-4 py-3 text-sm text-muted-foreground">
              Checking semantic index metadata...
            </div>
          ) : !semanticIndexed ? (
            <div className="rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
              This thing has not been indexed yet, so no semantic summary is
              available.
            </div>
          ) : semanticSummary ? (
            <div className="rounded-lg border bg-muted/20 px-4 py-3">
              <p className="whitespace-pre-line text-sm leading-6">
                {semanticSummary}
              </p>
            </div>
          ) : (
            <div className="rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
              The thing is indexed, but the stored semantic summary is empty.
            </div>
          )}

          {semanticIndexed && indexStatus?.stale ? (
            <p className="text-sm text-yellow-700">
              The semantic index snapshot is older than the current Thing
              Description and may be out of date.
            </p>
          ) : null}
        </div>

        <Separator />

        <div className="grid gap-6 xl:grid-cols-2">
          <SemanticBadgeList
            label="Location candidates"
            items={indexStatus?.location_candidates}
            emptyText="No locations inferred."
          />
          <SemanticBadgeList
            label="Indexed properties"
            items={indexStatus?.property_names}
            emptyText="No properties indexed."
          />
          <SemanticBadgeList
            label="Indexed actions"
            items={indexStatus?.action_names}
            emptyText="No actions indexed."
          />
          <SemanticBadgeList
            label="Indexed events"
            items={indexStatus?.event_names}
            emptyText="No events indexed."
          />
        </div>
      </CardContent>
    </Card>
  );
}
