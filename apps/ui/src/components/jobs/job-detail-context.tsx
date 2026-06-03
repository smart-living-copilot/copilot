'use client';

import { createContext, useCallback, useContext } from 'react';
import { useRouter } from 'next/navigation';

import { type JobRecord } from '@/lib/jobs-api';

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
  const router = useRouter();

  const openJobDetail = useCallback(
    (jobOrId: JobRecord | string) => {
      const jobId = typeof jobOrId === 'string' ? jobOrId : jobOrId.id;
      router.push(`/jobs/${encodeURIComponent(jobId)}`);
    },
    [router],
  );

  return (
    <JobDetailContext.Provider value={{ openJobDetail }}>
      {children}
    </JobDetailContext.Provider>
  );
}
