'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent } from '@/components/ui/card';
import { httpClient, httpJson } from '@/lib/http-client';
import { type ThingRecord, deleteThing, fetchThing } from '@/lib/things-api';

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

export function ThingDetail({ thingId }: { thingId: string }) {
  const router = useRouter();

  const [thing, setThing] = useState<ThingRecord | null>(null);
  const [isPending, setIsPending] = useState(true);
  const [isDeleting, setIsDeleting] = useState(false);
  const [indexStatus, setIndexStatus] = useState<ThingIndexStatus | null>(null);
  const [credentials, setCredentials] = useState<StoredCredential[]>([]);
  const [credDialogOpen, setCredDialogOpen] = useState(false);
  const [activeSecDef, setActiveSecDef] = useState<SecurityDefinition | null>(
    null,
  );

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
    if (!window.confirm(`Delete "${thing.title}"?`)) return;

    setIsDeleting(true);
    try {
      await deleteThing(thing.id);
      toast.success(`Deleted ${thing.title}`);
      router.push('/things');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Delete failed');
    } finally {
      setIsDeleting(false);
    }
  }, [router, thing]);

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

  if (isPending) {
    return (
      <Card>
        <CardContent className="flex min-h-64 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </CardContent>
      </Card>
    );
  }

  if (!thing || !detailData) {
    return (
      <Card>
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
  };

  return (
    <>
      <ThingDetailPageLayout {...sharedProps} />

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
