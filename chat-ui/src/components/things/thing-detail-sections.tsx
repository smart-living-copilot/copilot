'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { type ThingRecord } from '@/lib/things-api';

import {
  type ActionDef,
  type EventDef,
  type PropertyDef,
  type SecurityDefinition,
  type StoredCredential,
  type ThingIndexStatus,
} from './thing-detail-model';
import { ThingSemanticSection, ThingSummaryCard } from './thing-detail-summary';
import {
  ThingActionsSection,
  ThingEventsSection,
  ThingPropertiesSection,
  ThingSecuritySection,
} from './thing-detail-tables';

const DETAIL_TABS_TRIGGER_CLASSNAME =
  'flex-none rounded-none border-b-2 border-transparent px-4 py-2.5 font-medium text-muted-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none data-active:border-primary data-active:bg-transparent data-active:text-foreground data-active:shadow-none';

function getDefaultTabValue({
  properties,
  actions,
  events,
  semanticIndexed,
}: {
  properties: PropertyDef[];
  actions: ActionDef[];
  events: EventDef[];
  semanticIndexed: boolean;
}) {
  if (properties.length > 0) return 'properties';
  if (actions.length > 0) return 'actions';
  if (events.length > 0) return 'events';
  if (semanticIndexed) return 'semantic';
  return 'security';
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
}: ThingDetailLayoutProps) {
  const defaultTabValue = getDefaultTabValue({
    properties,
    actions,
    events,
    semanticIndexed,
  });

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <ThingSummaryCard
        thing={thing}
        title={title}
        description={description}
        securityStr={securityStr}
        properties={properties}
        actions={actions}
        events={events}
        indexStatus={indexStatus}
        isDeleting={isDeleting}
        onDelete={onDelete}
      />

      <Tabs defaultValue={defaultTabValue} className="space-y-6">
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
              value="actions"
              className={DETAIL_TABS_TRIGGER_CLASSNAME}
            >
              Actions ({actions.length})
            </TabsTrigger>
            <TabsTrigger
              value="events"
              className={DETAIL_TABS_TRIGGER_CLASSNAME}
            >
              Events ({events.length})
            </TabsTrigger>
            <TabsTrigger
              value="semantic"
              className={DETAIL_TABS_TRIGGER_CLASSNAME}
            >
              Semantic summary
            </TabsTrigger>
            <TabsTrigger
              value="security"
              className={DETAIL_TABS_TRIGGER_CLASSNAME}
            >
              Security ({securityDefs.length})
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="properties" className="mt-0">
          <ThingPropertiesSection properties={properties} />
        </TabsContent>

        <TabsContent value="actions" className="mt-0">
          <ThingActionsSection actions={actions} />
        </TabsContent>

        <TabsContent value="events" className="mt-0">
          <ThingEventsSection events={events} />
        </TabsContent>

        <TabsContent value="semantic" className="mt-0">
          <ThingSemanticSection
            indexStatus={indexStatus}
            semanticSummary={semanticSummary}
            semanticIndexed={semanticIndexed}
          />
        </TabsContent>

        <TabsContent value="security" className="mt-0">
          <ThingSecuritySection
            securityStr={securityStr}
            securityDefs={securityDefs}
            credentialMap={credentialMap}
            onDeleteCredential={onDeleteCredential}
            onOpenCredential={onOpenCredential}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
