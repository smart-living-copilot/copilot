'use client';

import { PanelsList } from '@/components/panels/panels-list';
import { AppShell } from '@/components/app-shell';

export default function PanelsPage() {
  return (
    <AppShell>
      <PanelsList />
    </AppShell>
  );
}
