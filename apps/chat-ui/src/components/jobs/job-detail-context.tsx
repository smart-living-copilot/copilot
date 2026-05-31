'use client';

import { createContext, useCallback, useContext, useState } from 'react';

import { JobDetailsDialog } from '@/components/jobs/job-details-dialog';
import { fetchJob, type JobRecord } from '@/lib/jobs-api';

interface JobDetailContextValue {
  openJobDetail: (jobOrId: JobRecord | string) => void;
}

const JobDetailContext = createContext<JobDetailContextValue | null>(null);

export function useJobDetail(): JobDetailContextValue {
  const ctx = useContext(JobDetailContext);
  if (!ctx) {
    throw new Error('useJobDetail must be used inside JobDetailProvider');
  }
  return ctx;
}

export function JobDetailProvider({ children }: { children: React.ReactNode }) {
  const [job, setJob] = useState<JobRecord | null>(null);

  const openJobDetail = useCallback(async (jobOrId: JobRecord | string) => {
    if (typeof jobOrId === 'string') {
      try {
        const fetched = await fetchJob(jobOrId);
        setJob(fetched);
      } catch {
        // If the fetch fails, silently ignore — no stale dialog shown.
      }
    } else {
      setJob(jobOrId);
    }
  }, []);

  return (
    <JobDetailContext.Provider value={{ openJobDetail }}>
      {children}
      <JobDetailsDialog job={job} onOpenChange={(open) => { if (!open) setJob(null); }} />
    </JobDetailContext.Provider>
  );
}
