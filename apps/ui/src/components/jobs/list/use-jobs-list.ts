import {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { toast } from 'sonner';

import {
  getJobSearchableText,
  getJobTabCounts,
  getJobTabLabel,
  jobMatchesTab,
  type JobTabCounts,
  type JobTabValue,
} from '@/components/jobs/list/job-list-formatters';
import { useJobEvents } from '@/hooks/use-job-events';
import { getJobStatus } from '@/lib/job-formatters';
import {
  type JobRecord,
  cancelJobRun,
  deleteJob,
  fetchJobs,
  runJobNow,
  setJobEnabled,
} from '@/lib/jobs-api';

export function useJobsList() {
  const [isHydrated, setIsHydrated] = useState(false);
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [activeTab, setActiveTab] = useState<JobTabValue>('all');
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [isPending, setIsPending] = useState(true);
  const [busyJobId, setBusyJobId] = useState<string | null>(null);
  const [runningJobId, setRunningJobId] = useState<string | null>(null);

  const upsertJob = useCallback((updated: JobRecord) => {
    setJobs((current) => {
      const index = current.findIndex((job) => job.id === updated.id);
      if (index === -1) {
        return [updated, ...current];
      }
      const next = current.slice();
      next[index] = updated;
      return next;
    });
  }, []);

  const loadJobs = useCallback(async () => {
    setIsPending(true);
    try {
      setJobs(await fetchJobs());
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to load jobs',
      );
    } finally {
      setIsPending(false);
    }
  }, []);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    setIsHydrated(true);
  }, []);

  useJobEvents(upsertJob);

  const now = useMemo(
    () => (isHydrated ? new Date() : new Date(0)),
    [isHydrated],
  );

  const searchedJobs = useMemo(() => {
    const query = deferredSearch.trim().toLowerCase();
    if (!query) return jobs;
    return jobs.filter((job) => getJobSearchableText(job).includes(query));
  }, [deferredSearch, jobs]);

  const visibleJobs = useMemo(
    () =>
      searchedJobs.filter((job) =>
        jobMatchesTab(activeTab, job, getJobStatus(job, now)),
      ),
    [activeTab, now, searchedJobs],
  );

  const tabCounts: JobTabCounts = useMemo(
    () => getJobTabCounts(searchedJobs, now),
    [now, searchedJobs],
  );

  const activeTabLabel = getJobTabLabel(activeTab);

  const handleRun = useCallback(async (jobId: string) => {
    setRunningJobId(jobId);
    setBusyJobId(jobId);
    try {
      await runJobNow(jobId);
      toast.success('Job run queued.');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to run job');
    } finally {
      setRunningJobId((current) => (current === jobId ? null : current));
      setBusyJobId((current) => (current === jobId ? null : current));
    }
  }, []);

  const handleToggleEnabled = useCallback(
    async (job: JobRecord) => {
      setBusyJobId(job.id);
      try {
        const updated = await setJobEnabled(job.id, !job.enabled);
        upsertJob(updated);
        toast.success(updated.enabled ? 'Job resumed.' : 'Job paused.');
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to update job',
        );
      } finally {
        setBusyJobId((current) => (current === job.id ? null : current));
      }
    },
    [upsertJob],
  );

  const handleCancel = useCallback(
    async (jobId: string) => {
      setBusyJobId(jobId);
      try {
        const updated = await cancelJobRun(jobId);
        upsertJob(updated);
        toast.success('Run cancelled.');
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to cancel run',
        );
      } finally {
        setBusyJobId((current) => (current === jobId ? null : current));
      }
    },
    [upsertJob],
  );

  const handleDelete = useCallback(async (job: JobRecord) => {
    setBusyJobId(job.id);
    try {
      await deleteJob(job.id);
      setJobs((current) => current.filter((item) => item.id !== job.id));
      toast.success('Job deleted.');
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to delete job',
      );
    } finally {
      setBusyJobId((current) => (current === job.id ? null : current));
    }
  }, []);

  return {
    activeTab,
    activeTabLabel,
    busyJobId,
    deferredSearch,
    isHydrated,
    isPending,
    runningJobId,
    search,
    setActiveTab,
    setSearch,
    tabCounts,
    visibleJobs,
    now,
    loadJobs,
    handleRun,
    handleToggleEnabled,
    handleCancel,
    handleDelete,
  };
}
