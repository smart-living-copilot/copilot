'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { type RJSFSchema } from '@rjsf/utils';
import { toast } from 'sonner';

import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { httpClient, httpJson } from '@/lib/http-client';
import { type ThingRecord, deleteThing, fetchThing } from '@/lib/things-api';
import { fetchSource } from '@/lib/sources-api';
import { isVirtualThingId } from '@/lib/virtual-things';
import { type RuntimeAffordanceType } from '@/lib/wot-runtime-api';
import {
  deleteVirtualThing,
  fetchVirtualThingDefinition,
  type VirtualThingBinding,
  type VirtualThingDefinition,
} from '@/lib/virtual-things-api';

import { BindingDrawer, bindingKey } from './binding-drawer';
import {
  RunAffordanceDialog,
  type RunAffordanceTarget,
} from './run-affordance-dialog';
import {
  ThingDetailPageLayout,
  type ThingDetailLayoutProps,
} from './thing-detail-sections';
import { CredentialDialog } from './thing-detail-credential-dialog';
import {
  parseActions,
  parseEvents,
  parseProperties,
  parseSecurityDefinitions,
  stringifyThingSecurity,
  type SecurityDefinition,
  type StoredCredential,
  type ThingIndexStatus,
} from './thing-detail-model';

function tabForBindingKey(
  key: string | null,
): 'properties' | 'events' | 'actions' | undefined {
  if (key?.startsWith('action:')) return 'actions';
  if (key?.startsWith('event:')) return 'events';
  if (key?.startsWith('property:')) return 'properties';
  return undefined;
}

/** Pull the input JSON Schema for an affordance out of the Thing Description. */
function inputSchemaFromDoc(
  doc: Record<string, unknown> | undefined,
  target: RunAffordanceTarget | null,
): RJSFSchema | null {
  if (!target) return null;
  const affordance = affordanceFromDoc(doc, target);
  if (!affordance) return null;
  const schema = (affordance as Record<string, unknown>)[
    target.affordanceType === 'action'
      ? 'input'
      : target.source === 'virtual'
        ? 'data'
        : 'subscription'
  ];
  return schema && typeof schema === 'object' ? (schema as RJSFSchema) : null;
}

function affordanceFromDoc(
  doc: Record<string, unknown> | undefined,
  target: RunAffordanceTarget | null,
): Record<string, unknown> | null {
  if (!doc || !target) return null;
  const collection =
    target.affordanceType === 'property'
      ? doc.properties
      : target.affordanceType === 'action'
        ? doc.actions
        : doc.events;
  if (!collection || typeof collection !== 'object') return null;
  const affordance = (collection as Record<string, unknown>)[
    target.affordanceName
  ];
  return affordance &&
    typeof affordance === 'object' &&
    !Array.isArray(affordance)
    ? (affordance as Record<string, unknown>)
    : null;
}

function uriVariablesSchemaFromDoc(
  doc: Record<string, unknown> | undefined,
  target: RunAffordanceTarget | null,
): RJSFSchema | null {
  const affordance = affordanceFromDoc(doc, target);
  const uriVariables = affordance?.uriVariables;
  if (
    !uriVariables ||
    typeof uriVariables !== 'object' ||
    Array.isArray(uriVariables)
  ) {
    return null;
  }
  return {
    type: 'object',
    properties: uriVariables as Record<string, RJSFSchema>,
  };
}

export function ThingDetail({
  thingId,
  onDeleted,
  variant = 'page',
}: {
  thingId: string;
  onDeleted?: (thingId: string) => void;
  /**
   * 'page' = standalone details page (binding editor opens in place).
   * 'drawer' = hosted in the compact detail drawer (binding deep-links to the
   * full page instead of stacking a second drawer).
   */
  variant?: 'page' | 'drawer';
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [thing, setThing] = useState<ThingRecord | null>(null);
  const [isPending, setIsPending] = useState(true);
  const [isDeleting, setIsDeleting] = useState(false);
  const [indexStatus, setIndexStatus] = useState<ThingIndexStatus | null>(null);
  const [credentials, setCredentials] = useState<StoredCredential[]>([]);
  const [credDialogOpen, setCredDialogOpen] = useState(false);
  const [activeSecDef, setActiveSecDef] = useState<SecurityDefinition | null>(
    null,
  );
  const [definition, setDefinition] = useState<VirtualThingDefinition | null>(
    null,
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeBindingKey, setActiveBindingKey] = useState<string | null>(null);
  const [runTarget, setRunTarget] = useState<RunAffordanceTarget | null>(null);
  const [runOpen, setRunOpen] = useState(false);
  const [refreshSupported, setRefreshSupported] = useState(false);

  const isVirtual = isVirtualThingId(thingId);

  useEffect(() => {
    let cancelled = false;

    setThing(null);
    setIsPending(true);

    fetchThing(thingId)
      .then((data) => {
        if (!cancelled) {
          setThing(data);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          toast.error(
            error instanceof Error ? error.message : 'Failed to load thing',
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsPending(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [thingId]);

  useEffect(() => {
    const sourceId = thing?.origin.source_id;
    if (!sourceId) {
      setRefreshSupported(false);
      return;
    }
    let cancelled = false;
    fetchSource(sourceId)
      .then((source) => {
        if (!cancelled) {
          setRefreshSupported(source.capabilities.includes('refresh'));
        }
      })
      .catch(() => {
        if (!cancelled) setRefreshSupported(false);
      });
    return () => {
      cancelled = true;
    };
  }, [thing]);

  useEffect(() => {
    if (!thing?.id) return;

    let cancelled = false;
    setIndexStatus(null);

    httpJson<ThingIndexStatus>(`/index-status/${encodeURIComponent(thingId)}`)
      .then((data) => {
        if (!cancelled) {
          setIndexStatus(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setIndexStatus({ thing_id: thingId, indexed: false });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [thingId, thing?.id]);

  const fetchCredentials = useCallback(async () => {
    try {
      const data = await httpJson<{ items: StoredCredential[] }>(
        `/credentials/${encodeURIComponent(thingId)}`,
      );
      setCredentials(data.items);
    } catch {
      setCredentials([]);
    }
  }, [thingId]);

  useEffect(() => {
    void fetchCredentials();
  }, [fetchCredentials]);

  useEffect(() => {
    if (!isVirtual) {
      setDefinition(null);
      return;
    }
    let cancelled = false;
    fetchVirtualThingDefinition(thingId, true)
      .then((data) => {
        if (!cancelled) setDefinition(data);
      })
      .catch(() => {
        if (!cancelled) setDefinition(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isVirtual, thingId]);

  const bindingMap = useMemo(() => {
    if (!definition) return undefined;
    return new Map<string, VirtualThingBinding>(
      definition.bindings.map((binding) => [bindingKey(binding), binding]),
    );
  }, [definition]);

  const setBindingParam = useCallback(
    (key: string | null) => {
      const params = new URLSearchParams(Array.from(searchParams.entries()));
      if (key) params.set('binding', key);
      else params.delete('binding');
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname, searchParams],
  );

  // Open the editor in place (full details page).
  const handleOpenBinding = useCallback(
    (key: string) => {
      setActiveBindingKey(key);
      setDrawerOpen(true);
      setBindingParam(key);
    },
    [setBindingParam],
  );

  // Deep-link target to the full page (compact drawer context).
  const buildBindingHref = useCallback(
    (key: string) =>
      `/things/${encodeURIComponent(thingId)}?binding=${encodeURIComponent(key)}`,
    [thingId],
  );

  const handleRun = useCallback(
    (affordanceType: RuntimeAffordanceType, name: string) => {
      const key = `${affordanceType}:${name}`;
      const binding = bindingMap?.get(key);
      setRunTarget({
        thingId,
        affordanceType,
        affordanceName: name,
        source: isVirtual ? 'virtual' : 'runtime',
        kind: binding?.kind,
      });
      setRunOpen(true);
    },
    [bindingMap, isVirtual, thingId],
  );

  // Auto-open the editor when arriving via a ?binding= deep link (page only).
  const deepLinkBinding =
    variant === 'page' ? searchParams.get('binding') : null;
  useEffect(() => {
    if (!deepLinkBinding || !bindingMap?.has(deepLinkBinding)) return;
    setActiveBindingKey(deepLinkBinding);
    setDrawerOpen(true);
  }, [deepLinkBinding, bindingMap]);

  const doc = thing?.document as Record<string, unknown> | undefined;

  const detailData = useMemo(() => {
    if (!thing || !doc) {
      return null;
    }

    const title =
      typeof doc.title === 'string' ? doc.title : thing.title || 'Untitled';
    const description =
      typeof doc.description === 'string' && doc.description.trim()
        ? doc.description
        : 'No description provided.';
    const properties = parseProperties(doc);
    const actions = parseActions(doc);
    const events = parseEvents(doc);
    const securityDefs = parseSecurityDefinitions(doc);
    const securityStr = stringifyThingSecurity(doc.security);

    return {
      actions,
      description,
      events,
      properties,
      securityDefs,
      securityStr,
      title,
    };
  }, [doc, thing]);

  const credentialMap = useMemo(
    () =>
      new Map(
        credentials.map((credential) => [credential.security_name, credential]),
      ),
    [credentials],
  );

  const handleDelete = useCallback(async () => {
    if (!thing) return;

    setIsDeleting(true);
    try {
      await (isVirtualThingId(thing.id)
        ? deleteVirtualThing(thing.id)
        : deleteThing(thing.id));
      toast.success(`Deleted ${thing.title}`);
      if (onDeleted) {
        onDeleted(thing.id);
      } else {
        router.push('/things');
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Delete failed');
    } finally {
      setIsDeleting(false);
    }
  }, [onDeleted, router, thing]);

  const handleDeleteCredential = useCallback(
    async (securityName: string) => {
      try {
        await httpClient(
          `/credentials/${encodeURIComponent(thingId)}/${encodeURIComponent(securityName)}`,
          { method: 'DELETE' },
        );
        toast.success(`Removed credentials for ${securityName}`);
        await fetchCredentials();
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to remove',
        );
      }
    },
    [fetchCredentials, thingId],
  );

  const handleOpenCredential = useCallback((definition: SecurityDefinition) => {
    setActiveSecDef(definition);
    setCredDialogOpen(true);
  }, []);

  const handleRefreshed = useCallback(async () => {
    const [data] = await Promise.all([fetchThing(thingId), fetchCredentials()]);
    setThing(data);
  }, [fetchCredentials, thingId]);

  if (isPending) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-44 rounded-md" />
        <Skeleton className="h-72 rounded-md" />
      </div>
    );
  }

  if (!thing || !detailData) {
    return (
      <Card className="rounded-md border-border/70">
        <CardContent className="flex min-h-64 flex-col items-center justify-center gap-4">
          <p className="text-muted-foreground">Thing not found.</p>
        </CardContent>
      </Card>
    );
  }

  const semanticSummary = indexStatus?.summary?.trim();
  const semanticIndexed = Boolean(indexStatus?.indexed);

  const sharedProps: ThingDetailLayoutProps = {
    thing,
    title: detailData.title,
    description: detailData.description,
    securityStr: detailData.securityStr,
    properties: detailData.properties,
    actions: detailData.actions,
    events: detailData.events,
    securityDefs: detailData.securityDefs,
    credentialMap,
    indexStatus,
    semanticSummary,
    semanticIndexed,
    isDeleting,
    onDelete: handleDelete,
    onDeleteCredential: handleDeleteCredential,
    onOpenCredential: handleOpenCredential,
    refreshSupported,
    onRefreshed: handleRefreshed,
    isVirtual,
    openHref:
      variant === 'drawer'
        ? `/things/${encodeURIComponent(thingId)}`
        : undefined,
    bindings: isVirtual ? bindingMap : undefined,
    onRun: handleRun,
    runRequiresBinding: isVirtual,
    onOpenBinding:
      isVirtual && variant === 'page' ? handleOpenBinding : undefined,
    bindingHref:
      isVirtual && variant === 'drawer' ? buildBindingHref : undefined,
    activeBindingKey: isVirtual ? activeBindingKey : null,
    defaultTab:
      variant === 'page' ? tabForBindingKey(deepLinkBinding) : undefined,
  };

  return (
    <>
      <ThingDetailPageLayout {...sharedProps} />

      {isVirtual && variant === 'page' ? (
        <BindingDrawer
          definition={definition}
          activeKey={activeBindingKey}
          open={drawerOpen}
          onOpenChange={(next) => {
            setDrawerOpen(next);
            if (!next) setBindingParam(null);
          }}
          onSaved={setDefinition}
        />
      ) : null}

      <RunAffordanceDialog
        target={runTarget}
        inputSchema={inputSchemaFromDoc(doc, runTarget)}
        uriVariablesSchema={uriVariablesSchemaFromDoc(doc, runTarget)}
        open={runOpen}
        onOpenChange={setRunOpen}
      />

      {activeSecDef ? (
        <CredentialDialog
          open={credDialogOpen}
          onOpenChange={setCredDialogOpen}
          thingId={thingId}
          secDef={activeSecDef}
          onSaved={() => void fetchCredentials()}
        />
      ) : null}
    </>
  );
}
