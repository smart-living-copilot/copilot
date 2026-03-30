'use client';

import { usePathname } from 'next/navigation';
import { AppSidebar } from '@/components/chat-sidebar';
import { SiteHeader, type BreadcrumbSegment } from '@/components/site-header';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';

function useBreadcrumbs(): BreadcrumbSegment[] {
  const pathname = usePathname();
  const segments: BreadcrumbSegment[] = [];

  if (pathname.startsWith('/things')) {
    segments.push({ label: 'Things', href: '/things' });

    if (pathname === '/things/create') {
      segments.push({ label: 'Create' });
    } else if (pathname === '/things/upload') {
      segments.push({ label: 'Upload' });
    } else if (pathname.endsWith('/edit')) {
      segments.push({ label: 'Edit' });
    } else if (pathname !== '/things') {
      segments.push({ label: 'Detail' });
    }
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
