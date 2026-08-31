'use client';

import {
  DatabaseZap,
  KeyRound,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react';
import { useCallback, useDeferredValue, useEffect, useState } from 'react';
import { toast } from 'sonner';

import { ConfirmDialog } from '@/components/confirm-dialog';
import { CredentialDialog } from '@/components/things/thing-detail-credential-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { httpClient } from '@/lib/http-client';
import {
  type DiscoverySource,
  deleteSource,
  fetchSources,
} from '@/lib/sources-api';

import { SourceRegistrationDialog } from './source-registration-dialog';

const PER_PAGE = 12;

export function SourcesList() {
  const [search, setSearch] = useState(
    () =>
      (typeof window === 'undefined'
        ? ''
        : new URLSearchParams(window.location.search).get('source')) || '',
  );
  const deferredSearch = useDeferredValue(search);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<DiscoverySource[]>([]);
  const [total, setTotal] = useState(0);
  const [pending, setPending] = useState(true);
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [editing, setEditing] = useState<DiscoverySource | null>(null);
  const [credentialSource, setCredentialSource] =
    useState<DiscoverySource | null>(null);

  useEffect(() => setPage(1), [deferredSearch]);

  const loadData = useCallback(async () => {
    setPending(true);
    try {
      const result = await fetchSources(page, PER_PAGE, deferredSearch);
      setData(result.data);
      setTotal(result.total);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to load sources',
      );
    } finally {
      setPending(false);
    }
  }, [deferredSearch, page]);

  useEffect(() => void loadData(), [loadData]);

  async function handleDelete(source: DiscoverySource) {
    try {
      await deleteSource(source.source_id);
      toast.success(`Deleted ${source.title}`);
      await loadData();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Delete failed');
    }
  }

  async function handleDeleteCredential(source: DiscoverySource) {
    try {
      await httpClient(
        `/discovery/sources/${encodeURIComponent(source.source_id)}/credentials/${encodeURIComponent(source.security_name)}`,
        { method: 'DELETE' },
      );
      toast.success(`Removed credentials for ${source.title}`);
      await loadData();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Could not remove credentials',
      );
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">Sources</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Manage persistent external discovery endpoints. Sources stay out of
            the Thing catalog until a resource is onboarded.
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => setRegistrationOpen(true)}>
            <Plus className="h-4 w-4" /> Register source
          </Button>
          <Button
            variant="outline"
            onClick={() => void loadData()}
            disabled={pending}
          >
            <RefreshCw
              className={pending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
            />
            Refresh
          </Button>
        </div>
      </section>

      <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
        <CardContent className="space-y-4 p-4 md:p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="relative w-full max-w-xl">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search sources"
                className="pl-9"
              />
            </div>
            <Badge variant="secondary">{total} total</Badge>
          </div>

          {pending ? (
            <div className="space-y-2 rounded-md border p-3">
              {['s1', 's2', 's3'].map((key) => (
                <Skeleton key={key} className="h-16 w-full rounded-md" />
              ))}
            </div>
          ) : data.length ? (
            <div className="overflow-x-auto rounded-md border">
              <Table className="min-w-[960px]">
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>Network</TableHead>
                    <TableHead>Credentials</TableHead>
                    <TableHead>Things</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.map((source) => (
                    <TableRow key={source.source_id} id={source.source_id}>
                      <TableCell>
                        <div className="space-y-1">
                          <div className="flex items-center gap-2 font-medium">
                            <DatabaseZap className="h-4 w-4 text-muted-foreground" />
                            {source.title}
                          </div>
                          <p className="line-clamp-2 max-w-xl text-sm text-muted-foreground">
                            {source.description || source.external_id}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          <Badge variant="outline">{source.provider}</Badge>
                          {source.capabilities.includes('refresh') ? (
                            <Badge variant="secondary">refresh</Badge>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell>{source.network_access}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            source.credential_status === 'required'
                              ? 'destructive'
                              : 'secondary'
                          }
                        >
                          {source.credential_status.replace('_', ' ')}
                        </Badge>
                      </TableCell>
                      <TableCell>{source.dependent_thing_count}</TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-2">
                          {source.security_scheme !== 'nosec' ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setCredentialSource(source)}
                            >
                              <KeyRound className="h-3.5 w-3.5" /> Credentials
                            </Button>
                          ) : null}
                          {source.credential_status === 'configured' ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                void handleDeleteCredential(source)
                              }
                            >
                              Clear credential
                            </Button>
                          ) : null}
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setEditing(source)}
                          >
                            <Pencil className="h-3.5 w-3.5" /> Edit
                          </Button>
                          <ConfirmDialog
                            destructive
                            confirmLabel="Remove"
                            description="This removes the source and its stored credentials. Sources with dependent Things cannot be removed."
                            onConfirm={() => handleDelete(source)}
                            title={`Remove "${source.title}"?`}
                            trigger={
                              <Button size="sm" variant="destructive">
                                <Trash2 className="h-3.5 w-3.5" /> Remove
                              </Button>
                            }
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="rounded-md border border-dashed px-6 py-12 text-center">
              <h2 className="text-xl font-semibold">No sources found</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Register a catalog, ToolHive registry, or dataspace endpoint.
              </p>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((value) => value + 1)}
            >
              Next
            </Button>
          </div>
        </CardContent>
      </Card>

      <SourceRegistrationDialog
        open={registrationOpen || editing !== null}
        onOpenChange={(next) => {
          setRegistrationOpen(next);
          if (!next) setEditing(null);
        }}
        source={editing}
        onRegistered={() => void loadData()}
      />

      {credentialSource ? (
        <CredentialDialog
          open
          onOpenChange={(next) => {
            if (!next) setCredentialSource(null);
          }}
          sourceId={credentialSource.source_id}
          secDef={{
            name: credentialSource.security_name,
            scheme: credentialSource.security_scheme,
          }}
          onSaved={() => {
            setCredentialSource(null);
            void loadData();
          }}
        />
      ) : null}
    </div>
  );
}
