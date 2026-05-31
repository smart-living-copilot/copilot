'use client';

import { use } from 'react';
import { ThingEditor } from '@/components/things/thing-editor';
import { AppShell } from '@/components/app-shell';

export default function EditThingPage({
  params,
}: {
  params: Promise<{ thingId: string }>;
}) {
  const { thingId } = use(params);

  return (
    <AppShell>
      <ThingEditor mode="edit" thingId={decodeURIComponent(thingId)} />
    </AppShell>
  );
}
