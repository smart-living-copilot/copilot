'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { type ReactNode } from 'react';
import { Pencil, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Spinner } from '@/components/ui/spinner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { type ThingRecord } from '@/lib/things-api';
import { withReturnTo } from '@/lib/return-to';

import {
  type ActionDef,
  type EventDef,
  type PropertyDef,
  type SecurityDefinition,
  type StoredCredential,
  type ThingIndexStatus,
  formatDateTime,
} from './thing-detail-model';
import { ThingSemanticSection } from './thing-detail-summary';
import {
  ThingActionsSection,
  ThingEventsSection,
  ThingPropertiesSection,
  ThingSecuritySection,
} from './thing-detail-tables';
import { ThingIndexStatusBadge } from './thing-index-status-badge';
import { VirtualThingStatusToggle } from './virtual-thing-status-toggle';

const DETAIL_TABS_TRIGGER_CLASSNAME =
  'flex-none rounded-none border-b-2 border-transparent px-4 py-2.5 font-medium text-muted-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none data-active:border-primary data-active:bg-transparent data-active:text-foreground data-active:shadow-none';

function FieldCard({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <Card
      size="sm"
      className="rounded-md border-border/70 shadow-sm shadow-black/5 xl:min-w-0 xl:flex-1 xl:basis-0"
    >
      <CardContent>
        <div className="text-xs text-muted-foreground">{label}</div>
        <div
          className={
            mono
              ? 'mt-1 break-all font-mono text-xs leading-5 text-foreground'
              : 'mt-1 truncate text-sm font-medium text-foreground'
          }
        >
          {value}
        </div>
      </CardContent>
    </Card>
  );
}

export interface ThingDetailLayoutProps {
  thing: ThingRecord;
  title: string;
  description: string;
  securityStr: string;
  properties: PropertyDef[];
  actions: ActionDef[];
  events: EventDef[];
  securityDefs: SecurityDefinition[];
  credentialMap: Map<string, StoredCredential>;
  indexStatus: ThingIndexStatus | null;
  semanticSummary?: string;
  semanticIndexed: boolean;
  isDeleting: boolean;
  onDelete: () => Promise<void> | void;
  onDeleteCredential: (securityName: string) => Promise<void> | void;
  onOpenCredential: (definition: SecurityDefinition) => void;
  isVirtual?: boolean;
}

export function ThingDetailPageLayout({
  thing,
  title,
  description,
  securityStr,
  properties,
  actions,
  events,
  securityDefs,
  credentialMap,
  indexStatus,
  semanticSummary,
  semanticIndexed,
  isDeleting,
  onDelete,
  onDeleteCredential,
  onOpenCredential,
  isVirtual = false,
}: ThingDetailLayoutProps) {
  const pathname = usePathname();
  const editHref = withReturnTo(
    isVirtual
      ? `/virtual-things/${encodeURIComponent(thing.id)}/edit`
      : `/things/${encodeURIComponent(thing.id)}/edit`,
    pathname,
  );

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
            <p className="break-all font-mono text-xs text-muted-foreground">
              {thing.id}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ThingIndexStatusBadge status={indexStatus} />
            {isVirtual ? <Badge variant="secondary">Virtual</Badge> : null}
            <Badge variant="outline">Security {securityStr}</Badge>
            <Badge variant="outline">
              {properties.length} propert{properties.length === 1 ? 'y' : 'ies'}
            </Badge>
            <Badge variant="outline">
              {actions.length} action{actions.length === 1 ? '' : 's'}
            </Badge>
            <Badge variant="outline">
              {events.length} event{events.length === 1 ? '' : 's'}
            </Badge>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isVirtual ? <VirtualThingStatusToggle thingId={thing.id} /> : null}
          <Button asChild variant="outline">
            <Link href={editHref}>
              <Pencil className="h-4 w-4" />
              {isVirtual ? 'Edit bindings' : 'Edit JSON'}
            </Link>
          </Button>
          <ConfirmDialog
            destructive
            confirmLabel={isDeleting ? 'Removing...' : 'Remove'}
            description={
              isVirtual
                ? 'This permanently removes the Virtual Thing definition, bindings, and produced Thing. This cannot be undone.'
                : 'This permanently removes the Thing Description and related credentials. This cannot be undone.'
            }
            onConfirm={onDelete}
            title={`Remove "${thing.title}"?`}
            trigger={
              <Button variant="destructive" disabled={isDeleting}>
                {isDeleting ? (
                  <Spinner className="size-4" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                {isDeleting ? 'Removing...' : 'Remove Thing'}
              </Button>
            }
          />
        </div>
      </section>

      <section className="space-y-4">
        <section className="grid gap-2 sm:grid-cols-2 xl:flex xl:flex-nowrap">
          <FieldCard
            label="Index status"
            value={<ThingIndexStatusBadge status={indexStatus} />}
          />
          <FieldCard label="Security" value={securityStr} />
          <FieldCard
            label="Indexed at"
            value={formatDateTime(indexStatus?.indexed_at)}
          />
          <FieldCard
            label="Summary model"
            value={indexStatus?.summary_model || 'Not indexed'}
          />
          <FieldCard label="Thing ID" value={thing.id} mono />
        </section>

        <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
          <CardHeader className="border-b border-border/70">
            <CardTitle className="text-base">Description</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
              {description || 'No description provided.'}
            </p>
          </CardContent>
        </Card>
      </section>

      <ThingSecuritySection
        securityStr={securityStr}
        securityDefs={securityDefs}
        credentialMap={credentialMap}
        onDeleteCredential={onDeleteCredential}
        onOpenCredential={onOpenCredential}
      />

      <Tabs defaultValue="properties" className="space-y-5">
        <div className="overflow-x-auto">
          <TabsList
            variant="line"
            className="h-auto min-w-max gap-0 rounded-none border-b border-border/80 bg-transparent p-0"
          >
            <TabsTrigger
              value="properties"
              className={DETAIL_TABS_TRIGGER_CLASSNAME}
            >
              Properties ({properties.length})
            </TabsTrigger>
            <TabsTrigger
              value="events"
              className={DETAIL_TABS_TRIGGER_CLASSNAME}
            >
              Events ({events.length})
            </TabsTrigger>
            <TabsTrigger
              value="actions"
              className={DETAIL_TABS_TRIGGER_CLASSNAME}
            >
              Actions ({actions.length})
            </TabsTrigger>
            <TabsTrigger
              value="semantic"
              className={DETAIL_TABS_TRIGGER_CLASSNAME}
            >
              Semantic Summary
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="properties" className="mt-0">
          <ThingPropertiesSection properties={properties} />
        </TabsContent>

        <TabsContent value="events" className="mt-0">
          <ThingEventsSection events={events} />
        </TabsContent>

        <TabsContent value="actions" className="mt-0">
          <ThingActionsSection actions={actions} />
        </TabsContent>

        <TabsContent value="semantic" className="mt-0">
          <ThingSemanticSection
            indexStatus={indexStatus}
            semanticSummary={semanticSummary}
            semanticIndexed={semanticIndexed}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
