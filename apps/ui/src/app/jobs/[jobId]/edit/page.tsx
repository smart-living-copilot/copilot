import { AppShell } from '@/components/app-shell';
import { JobEditPage } from '@/components/jobs/job-edit-page';

type PageProps = { params: Promise<{ jobId: string }> };

export default async function Page({ params }: PageProps) {
  const { jobId } = await params;
  return (
    <AppShell>
      <JobEditPage jobId={jobId} />
    </AppShell>
  );
}
