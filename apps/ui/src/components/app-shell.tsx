'use client';

import { useEffect, useMemo, useState } from 'react';
import { usePathname } from 'next/navigation';
import { AppSidebar } from '@/components/chat-sidebar';
import { SiteHeader, type BreadcrumbSegment } from '@/components/site-header';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { fetchJob } from '@/lib/jobs-api';
import { fetchThing } from '@/lib/things-api';

type RecordBreadcrumbTarget =
  | {
      href: string;
      id: string;
      kind: 'job';
    }
  | {
      href: string;
      id: string;
      kind: 'thing';
    };

function decodePathSegment(segment: string) {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

function getRecordBreadcrumbTarget(
  pathname: string,
): RecordBreadcrumbTarget | null {
  const segments = pathname.split('/').filter(Boolean);
  const [section, rawId] = segments;

  if (!rawId) {
    return null;
  }

  if (section === 'things' && rawId !== 'create' && rawId !== 'upload') {
    const id = decodePathSegment(rawId);
    return {
      href: `/things/${encodeURIComponent(id)}`,
      id,
      kind: 'thing',
    };
  }

  if (section === 'jobs' && rawId !== 'new') {
    const id = decodePathSegment(rawId);
    return {
      href: `/jobs/${encodeURIComponent(id)}`,
      id,
      kind: 'job',
    };
  }

  // Virtual Things live under /things; their logic editor lives at
  // /virtual-things/{id}/edit, so resolve the label and point the detail crumb
  // back at the shared Things detail page.
  if (section === 'virtual-things' && rawId) {
    const id = decodePathSegment(rawId);
    return {
      href: `/things/${encodeURIComponent(id)}`,
      id,
      kind: 'thing',
    };
  }

  return null;
}

function useRecordBreadcrumbLabel(target: RecordBreadcrumbTarget | null) {
  const [resolvedLabel, setResolvedLabel] = useState<{
    key: string;
    label: string | null;
  } | null>(null);
  const key = target ? `${target.kind}:${target.id}` : null;
  const id = target?.id;
  const kind = target?.kind;

  useEffect(() => {
    if (!id || !kind || !key) {
      return;
    }

    let cancelled = false;

    const request =
      kind === 'job'
        ? fetchJob(id).then((job) => job.name)
        : fetchThing(id).then((thing) => thing.title);

    void request
      .then((nextLabel) => {
        if (!cancelled) {
          setResolvedLabel({ key, label: nextLabel || null });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResolvedLabel({ key, label: null });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [id, key, kind]);

  return resolvedLabel?.key === key ? resolvedLabel.label : null;
}

function useBreadcrumbs(): BreadcrumbSegment[] {
  const pathname = usePathname();
  const target = useMemo(() => getRecordBreadcrumbTarget(pathname), [pathname]);
  const recordLabel = useRecordBreadcrumbLabel(target);
  const segments: BreadcrumbSegment[] = [];

  if (pathname.startsWith('/things')) {
    segments.push({ label: 'Things', href: '/things' });

    if (pathname === '/things/create') {
      segments.push({ label: 'Create' });
    } else if (target?.kind === 'thing' && pathname.endsWith('/edit')) {
      segments.push({
        label: recordLabel ?? 'Thing detail',
        href: target.href,
      });
      segments.push({ label: 'Edit' });
    } else if (target?.kind === 'thing') {
      segments.push({ label: recordLabel ?? 'Thing detail' });
    } else if (pathname !== '/things') {
      segments.push({ label: 'Detail' });
    }
  } else if (pathname.startsWith('/jobs')) {
    segments.push({ label: 'Jobs', href: '/jobs' });

    if (pathname === '/jobs/new') {
      segments.push({ label: 'Create' });
    } else if (target?.kind === 'job' && pathname.endsWith('/edit')) {
      segments.push({
        label: recordLabel ?? 'Job detail',
        href: target.href,
      });
      segments.push({ label: 'Edit' });
    } else if (target?.kind === 'job' && pathname.endsWith('/thread')) {
      segments.push({
        label: recordLabel ?? 'Job detail',
        href: target.href,
      });
      segments.push({ label: 'Thread' });
    } else if (target?.kind === 'job') {
      segments.push({ label: recordLabel ?? 'Job detail' });
    } else if (pathname !== '/jobs') {
      segments.push({ label: 'Detail' });
    }
  } else if (pathname.startsWith('/virtual-things')) {
    segments.push({ label: 'Things', href: '/things' });

    if (target?.kind === 'thing') {
      segments.push({
        label: recordLabel ?? 'Thing detail',
        href: target.href,
      });
      segments.push({ label: 'Edit bindings' });
    }
  } else if (pathname.startsWith('/panels')) {
    segments.push({ label: 'Panels', href: '/panels' });
  } else if (pathname.startsWith('/settings')) {
    segments.push({ label: 'Settings' });
  }

  return segments;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const breadcrumbs = useBreadcrumbs();

  return (
    <SidebarProvider className="relative h-dvh overflow-hidden text-foreground">
      <AppSidebar />
      <SidebarInset>
        <SiteHeader breadcrumbs={breadcrumbs} />
        <div className="flex-1 overflow-auto px-4 py-4 md:px-6 md:py-6">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
