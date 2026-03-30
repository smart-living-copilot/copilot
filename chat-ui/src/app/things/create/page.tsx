'use client';

import { ThingEditor } from '@/components/things/thing-editor';
import { AppShell } from '@/components/app-shell';

export default function CreateThingPage() {
  return (
    <AppShell>
      <ThingEditor mode="create" />
    </AppShell>
  );
}
