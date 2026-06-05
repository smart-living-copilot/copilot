'use client';

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
  const href = thingId ? `/things/${encodeURIComponent(thingId)}` : undefined;

  return (
    <DetailDrawerShell
      description={thingId ?? 'No thing selected'}
      fullPageHref={href}
      onOpenChange={onOpenChange}
      open={open}
      title="Thing Details"
      width="min(100vw, 64rem)"
    >
      {thingId ? <ThingDetail thingId={thingId} onDeleted={onDeleted} /> : null}
    </DetailDrawerShell>
  );
}
