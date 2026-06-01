'use client';

import { useCallback, useRef } from 'react';
import { toast } from 'sonner';

import { useJobDetail } from '@/components/jobs/job-detail-context';
import { useJobEvents } from '@/hooks/use-job-events';
import { type JobRecord } from '@/lib/jobs-api';

function summarizeResult(job: JobRecord): string {
  if (job.last_error?.trim()) {
    return job.last_error.trim();
  }

  if (job.last_response?.trim()) {
    const response = job.last_response.trim().replace(/\s+/g, ' ');
    return response.length > 140 ? `${response.slice(0, 137)}...` : response;
  }

  return 'Execution finished.';
}

export function JobTriggerToasts() {
  const { openJobDetail } = useJobDetail();
  const seenRunsRef = useRef<Set<string>>(new Set());

  const handleJob = useCallback(
    (job: JobRecord) => {
      const runKey = `${job.id}:${job.run_count}:${job.last_run_at ?? ''}`;
      if (seenRunsRef.current.has(runKey)) {
        return;
      }
      seenRunsRef.current.add(runKey);

      const detail = summarizeResult(job);
      const description = (
        <button
          type="button"
          className="w-full cursor-pointer text-left"
          onClick={() => openJobDetail(job.id)}
        >
          {detail}
        </button>
      );
      const action = {
        label: 'View details',
        onClick: () => openJobDetail(job.id),
      };

      if (job.last_error?.trim()) {
        toast.error(`Job failed: ${job.name}`, { description, action });
      } else {
        toast.success(`Job triggered: ${job.name}`, { description, action });
      }
    },
    [openJobDetail],
  );

  useJobEvents(handleJob);

  return null;
}
