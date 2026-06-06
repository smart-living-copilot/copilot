'use client';

import Link from 'next/link';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from '@/components/theme-provider';
import { JobNotificationsBell } from '@/components/jobs/job-notifications-bell';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { SidebarTrigger } from '@/components/ui/sidebar';

export interface BreadcrumbSegment {
  label: string;
  href?: string;
}

interface SiteHeaderProps {
  breadcrumbs?: BreadcrumbSegment[];
  children?: React.ReactNode;
}

export function SiteHeader({ breadcrumbs = [], children }: SiteHeaderProps) {
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 px-4">
      <SidebarTrigger className="-ml-1" />

      {breadcrumbs.length > 0 && (
        <>
          <Separator orientation="vertical" className="mr-2 h-4" />
          <Breadcrumb>
            <BreadcrumbList>
              {breadcrumbs.map((segment, i) => {
                const isLast = i === breadcrumbs.length - 1;
                const key = `${segment.href ?? 'current'}-${segment.label}-${i}`;
                return isLast ? (
                  <BreadcrumbItem key={key}>
                    <BreadcrumbPage
                      className="max-w-[14rem] truncate md:max-w-[24rem]"
                      title={segment.label}
                    >
                      {segment.label}
                    </BreadcrumbPage>
                  </BreadcrumbItem>
                ) : (
                  <BreadcrumbItem key={key}>
                    {segment.href ? (
                      <BreadcrumbLink asChild>
                        <Link
                          className="max-w-[12rem] truncate md:max-w-[20rem]"
                          href={segment.href}
                          title={segment.label}
                        >
                          {segment.label}
                        </Link>
                      </BreadcrumbLink>
                    ) : (
                      <BreadcrumbPage
                        className="max-w-[12rem] truncate md:max-w-[20rem]"
                        title={segment.label}
                      >
                        {segment.label}
                      </BreadcrumbPage>
                    )}
                    <BreadcrumbSeparator />
                  </BreadcrumbItem>
                );
              })}
            </BreadcrumbList>
          </Breadcrumb>
        </>
      )}

      {children}

      <div className="ml-auto flex items-center gap-1">
        <JobNotificationsBell />
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
        >
          <Sun className="h-4 w-4 hidden dark:block" />
          <Moon className="h-4 w-4 block dark:hidden" />
          <span className="sr-only">Toggle theme</span>
        </Button>
      </div>
    </header>
  );
}
