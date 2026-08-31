'use client';

import { AppShell } from '@/components/app-shell';
import { SourcesList } from '@/components/sources/sources-list';

export default function SourcesPage() {
  return (
    <AppShell>
      <SourcesList />
    </AppShell>
  );
}
