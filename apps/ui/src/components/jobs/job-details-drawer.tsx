'use client';

import { DetailDrawerShell } from '@/components/detail-drawer-shell';
import { JobDetailsPage } from '@/components/jobs/job-details-page';

export function JobDetailsDrawer({
  jobId,
  open,
  onDeleted,
  onOpenChange,
}: {
  jobId: string | null;
  open: boolean;
  onDeleted: (jobId: string) => void;
  onOpenChange: (open: boolean) => void;
}) {
  const href = jobId ? `/jobs/${encodeURIComponent(jobId)}` : undefined;

  return (
    <DetailDrawerShell
      description={jobId ?? 'No job selected'}
      onOpenChange={onOpenChange}
      open={open}
      title="Job Details"
      width="min(100vw, 72rem)"
    >
      {jobId ? (
        <JobDetailsPage jobId={jobId} onDeleted={onDeleted} openHref={href} />
      ) : null}
    </DetailDrawerShell>
  );
}
