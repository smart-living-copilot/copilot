'use client';

import { Suspense } from 'react';

import { DetailDrawerShell } from '@/components/detail-drawer-shell';
import { ThingDetail } from '@/components/things/thing-detail';

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
  return (
    <DetailDrawerShell
      description={thingId ?? 'No thing selected'}
      onOpenChange={onOpenChange}
      open={open}
      title="Thing Details"
      width="min(100vw, 64rem)"
    >
      {thingId ? (
        <Suspense fallback={null}>
          <ThingDetail
            thingId={thingId}
            onDeleted={onDeleted}
            variant="drawer"
          />
        </Suspense>
      ) : null}
    </DetailDrawerShell>
  );
}
