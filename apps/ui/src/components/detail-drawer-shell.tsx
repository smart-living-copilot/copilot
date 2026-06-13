'use client';

import type { CSSProperties, ReactNode } from 'react';

import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer';

interface DetailDrawerShellProps {
  children: ReactNode;
  description: string;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  title: string;
  width: CSSProperties['width'];
}

export function DetailDrawerShell({
  children,
  description,
  onOpenChange,
  open,
  title,
  width,
}: DetailDrawerShellProps) {
  return (
    <Drawer direction="right" onOpenChange={onOpenChange} open={open}>
      <DrawerContent className="gap-0 p-0" style={{ width, maxWidth: 'none' }}>
        {/* The detail content renders its own heading; keep a screen-reader
            title/description so the dialog stays accessible. */}
        <DrawerHeader className="sr-only">
          <DrawerTitle>{title}</DrawerTitle>
          <DrawerDescription>{description}</DrawerDescription>
        </DrawerHeader>
        <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-5">
          {children}
        </div>
      </DrawerContent>
    </Drawer>
  );
}
