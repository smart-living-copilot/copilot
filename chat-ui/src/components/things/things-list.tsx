'use client';

import { useCallback, useDeferredValue, useEffect, useState } from 'react';
import Link from 'next/link';
import { Eye, Loader2, Plus, Search, Upload } from 'lucide-react';
import { toast } from 'sonner';

import { type ThingRecord, fetchThings } from '@/lib/things-api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { type ThingIndexStatus } from '@/components/things/thing-detail-model';
import { ThingIndexStatusBadge } from '@/components/things/thing-index-status-badge';

const PER_PAGE = 12;

export function ThingsList() {
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ThingRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [isPending, setIsPending] = useState(true);
  const [indexStatuses, setIndexStatuses] = useState<
    Record<string, ThingIndexStatus>
  >({});

  useEffect(() => {
    setPage(1);
  }, [deferredSearch]);

  const loadData = useCallback(async () => {
    setIsPending(true);
    try {
      const result = await fetchThings(page, PER_PAGE, deferredSearch);
      setData(result.data);
      setTotal(result.total);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to load things',
      );
    } finally {
      setIsPending(false);
    }
  }, [page, deferredSearch]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Lazy-load index statuses for visible things
  useEffect(() => {
    if (!data || data.length === 0) return;

    for (const record of data) {
      if (indexStatuses[record.id] !== undefined) continue;

      fetch(`/api/index-status/${encodeURIComponent(record.id)}`)
        .then((res) => (res.ok ? res.json() : null))
        .then((status) => {
          if (status) {
            setIndexStatuses((prev) => ({
              ...prev,
              [record.id]: status as ThingIndexStatus,
            }));
          }
        })
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));
  const hasSearch = deferredSearch.trim().length > 0;

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="w-full space-y-8">
          <div className="flex items-center gap-3">
            <div className="space-y-1">
              <h1 className="text-3xl font-semibold tracking-tight">Things</h1>
              <p className="text-sm text-muted-foreground">
                Browse and manage Thing Descriptions. View any thing to inspect
                or edit the full document.
              </p>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link href="/things/upload">
              <Upload className="h-4 w-4" />
              Upload
            </Link>
          </Button>
          <Button asChild>
            <Link href="/things/create">
              <Plus className="h-4 w-4" />
              Create
            </Link>
          </Button>
        </div>
      </section>

      <Card className="overflow-hidden">
        <CardContent className="space-y-4 p-6">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div className="relative w-full max-w-xl">
              <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by name, id, description, tags, or JSON..."
                className="pl-11"
              />
            </div>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <Badge variant="secondary" className="font-medium">
                {total} total
              </Badge>
              <span>
                Page {page} of {totalPages}
              </span>
            </div>
          </div>

          {isPending ? (
            <div className="flex min-h-48 items-center justify-center rounded-md border">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : data.length > 0 ? (
            <>
              <div className="rounded-md border">
                <Table className="min-w-[980px]">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[42%]">Thing</TableHead>
                      <TableHead className="w-[34%]">Identifier</TableHead>
                      <TableHead className="w-[16%]">Index status</TableHead>
                      <TableHead className="w-[8%] text-right">View</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.map((record) => (
                      <TableRow key={record.id}>
                        <TableCell className="min-w-[280px]">
                          <div className="space-y-1">
                            <Link
                              href={`/things/${encodeURIComponent(record.id)}`}
                              className="font-medium transition-colors hover:text-primary"
                            >
                              {record.title}
                            </Link>
                            <p className="line-clamp-2 max-w-xl text-sm leading-5 text-muted-foreground">
                              {record.description || 'No description provided.'}
                            </p>
                          </div>
                        </TableCell>
                        <TableCell className="max-w-[320px] font-mono text-xs text-muted-foreground">
                          <span className="block truncate">{record.id}</span>
                        </TableCell>
                        <TableCell>
                          <ThingIndexStatusBadge
                            status={indexStatuses[record.id]}
                          />
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center justify-end">
                            <Button asChild variant="outline" size="sm">
                              <Link
                                href={`/things/${encodeURIComponent(record.id)}`}
                              >
                                <Eye className="h-3.5 w-3.5" />
                                View
                              </Link>
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              <div className="flex flex-col gap-3 rounded-xl border bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-muted-foreground">
                  Showing {data.length} of {total} things
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((c) => Math.max(1, c - 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((c) => Math.min(totalPages, c + 1))}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className="rounded-lg border border-dashed px-6 py-12 text-center">
              <h2 className="text-2xl font-semibold tracking-tight">
                No things found
              </h2>
              <p className="mx-auto mt-2 max-w-md text-base text-muted-foreground">
                {hasSearch
                  ? `No things match "${deferredSearch.trim()}". Try another search or clear the filter.`
                  : 'Create the first Thing Description to get started.'}
              </p>
              <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
                {hasSearch && (
                  <Button variant="outline" onClick={() => setSearch('')}>
                    Clear search
                  </Button>
                )}
                <Button variant="outline" asChild>
                  <Link href="/things/upload">
                    <Upload className="h-4 w-4" />
                    Upload
                  </Link>
                </Button>
                <Button asChild>
                  <Link href="/things/create">
                    <Plus className="h-4 w-4" />
                    Create
                  </Link>
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
