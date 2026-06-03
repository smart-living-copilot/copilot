import { AppShell } from '@/components/app-shell';
import { JobDetailsPage } from '@/components/jobs/job-details-page';

type PageProps = { params: Promise<{ jobId: string }> };

export default async function Page({ params }: PageProps) {
  const { jobId } = await params;
  return (
    <AppShell>
      <JobDetailsPage jobId={jobId} />
    </AppShell>
  );
}
