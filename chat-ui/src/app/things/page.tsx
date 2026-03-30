'use client';

import { ThingsList } from '@/components/things/things-list';
import { AppShell } from '@/components/app-shell';

export default function ThingsPage() {
  return (
    <AppShell>
      <ThingsList />
    </AppShell>
  );
}
