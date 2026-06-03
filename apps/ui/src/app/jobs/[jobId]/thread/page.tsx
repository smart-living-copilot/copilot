import { AppShell } from '@/components/app-shell';
import { JobThreadPage } from '@/components/jobs/job-thread-page';

type PageProps = { params: Promise<{ jobId: string }> };

export default async function Page({ params }: PageProps) {
  const { jobId } = await params;
  return (
    <AppShell>
      <JobThreadPage jobId={jobId} />
    </AppShell>
  );
}
