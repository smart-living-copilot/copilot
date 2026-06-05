'use client';

import { DashboardsList } from '@/components/dashboards/dashboards-list';
import { AppShell } from '@/components/app-shell';

export default function DashboardsPage() {
  return (
    <AppShell>
      <DashboardsList />
    </AppShell>
  );
}
