'use client';

import Link from 'next/link';
import { useTheme } from 'next-themes';
import { Moon, Sun } from 'lucide-react';
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
                return isLast ? (
                  <BreadcrumbItem key={segment.label}>
                    <BreadcrumbPage>{segment.label}</BreadcrumbPage>
                  </BreadcrumbItem>
                ) : (
                  <BreadcrumbItem key={segment.label}>
                    {segment.href ? (
                      <BreadcrumbLink asChild>
                        <Link href={segment.href}>{segment.label}</Link>
                      </BreadcrumbLink>
                    ) : (
                      <BreadcrumbPage>{segment.label}</BreadcrumbPage>
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

      <div className="ml-auto">
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
