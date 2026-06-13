'use client';

import { Suspense, use } from 'react';
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
      <Suspense fallback={null}>
        <ThingDetail thingId={decodeURIComponent(thingId)} />
      </Suspense>
    </AppShell>
  );
}
