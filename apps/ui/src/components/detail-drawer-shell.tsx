'use client';

import type { CSSProperties, ReactNode } from 'react';
import Link from 'next/link';
import { ExternalLink, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer';

interface DetailDrawerShellProps {
  children: ReactNode;
  description: string;
  fullPageHref?: string;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  title: string;
  width: CSSProperties['width'];
}

export function DetailDrawerShell({
  children,
  description,
  fullPageHref,
  onOpenChange,
  open,
  title,
  width,
}: DetailDrawerShellProps) {
  return (
    <Drawer direction="right" onOpenChange={onOpenChange} open={open}>
      <DrawerContent className="gap-0 p-0" style={{ width, maxWidth: 'none' }}>
        <DrawerHeader className="flex-row items-start justify-between gap-3 border-b border-border/70 px-4 py-3">
          <div className="min-w-0">
            <DrawerTitle className="text-sm">{title}</DrawerTitle>
            <DrawerDescription className="truncate font-mono text-xs">
              {description}
            </DrawerDescription>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {fullPageHref ? (
              <Button asChild size="sm" variant="outline">
                <Link href={fullPageHref}>
                  <ExternalLink className="size-3.5" />
                  Open full page
                </Link>
              </Button>
            ) : null}
            <DrawerClose asChild>
              <Button aria-label="Close" size="icon-sm" variant="ghost">
                <X />
              </Button>
            </DrawerClose>
          </div>
        </DrawerHeader>
        <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-5">
          {children}
        </div>
      </DrawerContent>
    </Drawer>
  );
}
