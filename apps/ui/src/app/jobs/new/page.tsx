'use client';

import { AppShell } from '@/components/app-shell';
import { JobCreatePage } from '@/components/jobs/job-create-page';

export default function NewJobPage() {
  return (
    <AppShell>
      <JobCreatePage />
    </AppShell>
  );
}
