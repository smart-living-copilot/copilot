'use client';

import { AppShell } from '@/components/app-shell';
import { JobsList } from '@/components/jobs/jobs-list';

export default function JobsPage() {
  return (
    <AppShell>
      <JobsList />
    </AppShell>
  );
}
