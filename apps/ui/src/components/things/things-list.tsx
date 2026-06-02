'use client';

import { useCallback, useDeferredValue, useEffect, useState } from 'react';
import Link from 'next/link';
import { Eye, Plus, RefreshCw, Search, Upload } from 'lucide-react';
import { toast } from 'sonner';

import { type ThingRecord, fetchThings } from '@/lib/things-api';
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
    <div className="space-y-5">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">Things</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Browse and manage Thing Descriptions. View any thing to inspect or
            edit the full document.
          </p>
        </div>
        <div className="flex items-center gap-2">
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
          <Button
            variant="outline"
            onClick={() => void loadData()}
            disabled={isPending}
          >
            <RefreshCw
              className={isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
            />
            Refresh
          </Button>
        </div>
      </section>

      <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
        <CardContent className="space-y-4 p-4 md:p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative w-full lg:max-w-xl">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search things"
                className="pl-9"
              />
            </div>
            <div className="flex min-h-8 items-center gap-2 text-sm text-muted-foreground">
              <Badge variant="secondary">{total} total</Badge>
              <Badge variant="outline">
                Page {page} of {totalPages}
              </Badge>
            </div>
          </div>

          {isPending ? (
            <div className="space-y-2 rounded-md border p-3">
              {['r1', 'r2', 'r3', 'r4', 'r5'].map((key) => (
                <Skeleton key={key} className="h-12 w-full rounded-md" />
              ))}
            </div>
          ) : data.length > 0 ? (
            <>
              <div className="overflow-x-auto rounded-md border">
                <Table className="min-w-[980px] table-fixed">
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

              <div className="flex flex-col gap-3 rounded-md border bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
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
            <div className="rounded-md border border-dashed px-6 py-12 text-center">
              <h2 className="text-xl font-semibold tracking-tight">
                No things found
              </h2>
              <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
                {hasSearch
                  ? `No things match "${deferredSearch.trim()}".`
                  : 'Create the first Thing Description to get started.'}
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
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
