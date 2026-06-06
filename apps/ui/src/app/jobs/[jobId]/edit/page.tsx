import { AppShell } from '@/components/app-shell';
import { JobEditPage } from '@/components/jobs/job-edit-page';
import { getFirstSearchParam } from '@/lib/return-to';

type PageProps = {
  params: Promise<{ jobId: string }>;
  searchParams: Promise<{ returnTo?: string | string[] }>;
};

export default async function Page({ params, searchParams }: PageProps) {
  const [{ jobId }, query] = await Promise.all([params, searchParams]);
  return (
    <AppShell>
      <JobEditPage
        jobId={jobId}
        returnTo={getFirstSearchParam(query.returnTo)}
      />
    </AppShell>
  );
}
