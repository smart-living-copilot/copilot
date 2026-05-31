'use client';

import { use } from 'react';
import { ThingDetail } from '@/components/things/thing-detail';
import { AppShell } from '@/components/app-shell';

export default function ThingDetailPage({
  params,
}: {
  params: Promise<{ thingId: string }>;
}) {
  const { thingId } = use(params);

  return (
    <AppShell>
      <ThingDetail thingId={decodeURIComponent(thingId)} />
    </AppShell>
  );
}
