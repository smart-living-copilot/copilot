'use client';

import Link from 'next/link';
import { ExternalLink, X } from 'lucide-react';

import { ThingDetail } from '@/components/things/thing-detail';
import { Button } from '@/components/ui/button';
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer';

export function ThingDetailDrawer({
  thingId,
  open,
  onDeleted,
  onOpenChange,
}: {
  thingId: string | null;
  open: boolean;
  onDeleted: (thingId: string) => void;
  onOpenChange: (open: boolean) => void;
}) {
  const href = thingId ? `/things/${encodeURIComponent(thingId)}` : '/things';

  return (
    <Drawer direction="right" onOpenChange={onOpenChange} open={open}>
      <DrawerContent
        className="gap-0 p-0"
        style={{ width: 'min(100vw, 64rem)', maxWidth: 'none' }}
      >
        <DrawerHeader className="flex-row items-start justify-between gap-3 border-b border-border/70 px-4 py-3">
          <div className="min-w-0">
            <DrawerTitle className="text-sm">Thing Details</DrawerTitle>
            <DrawerDescription className="truncate font-mono text-xs">
              {thingId ?? 'No thing selected'}
            </DrawerDescription>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {thingId ? (
              <Button asChild size="sm" variant="outline">
                <Link href={href}>
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
          {thingId ? (
            <ThingDetail thingId={thingId} onDeleted={onDeleted} />
          ) : null}
        </div>
      </DrawerContent>
    </Drawer>
  );
}
