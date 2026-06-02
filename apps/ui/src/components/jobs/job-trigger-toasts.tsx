'use client';

import { useCallback, useRef } from 'react';
import { toast } from 'sonner';

import { useJobDetail } from '@/components/jobs/job-detail-context';
import { JobToastContent } from '@/components/jobs/job-toast-content';
import { useSpeechPlayback } from '@/components/jobs/speech-playback-context';
import { useJobEvents } from '@/hooks/use-job-events';
import { type JobRecord } from '@/lib/jobs-api';

const SEEN_RUNS_LIMIT = 200;

function summarizeResult(job: JobRecord): string {
  if (job.last_run_status === 'waiting_for_input') {
    return (
      job.waiting_question?.trim() || 'The job is waiting for your answer.'
    );
  }

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
  const { voiceMode, play } = useSpeechPlayback();
  const seenRunsRef = useRef<Set<string>>(new Set());

  const handleJob = useCallback(
    (job: JobRecord) => {
      const runKey = [
        job.id,
        job.last_run_id ?? job.active_run_id ?? job.run_count,
        job.last_run_status ?? '',
        job.last_run_at ?? '',
      ].join(':');
      if (seenRunsRef.current.has(runKey)) {
        return;
      }
      seenRunsRef.current.add(runKey);
      if (seenRunsRef.current.size > SEEN_RUNS_LIMIT) {
        const oldest = seenRunsRef.current.values().next().value;
        if (oldest !== undefined) {
          seenRunsRef.current.delete(oldest);
        }
      }

      const detail = summarizeResult(job);
      const toastId = `job-toast:${runKey}`;
      const isWaiting = job.last_run_status === 'waiting_for_input';
      const description = (
        <JobToastContent
          job={job}
          detail={detail}
          onOpen={() => openJobDetail(job.id)}
          onAnswered={() => toast.dismiss(toastId)}
        />
      );
      const action = {
        label: 'View details',
        onClick: () => openJobDetail(job.id),
      };
      // Interactive toasts (answer form) and failures must persist so they are
      // not dismissed mid-interaction; successes can auto-dismiss.
      const options = {
        id: toastId,
        description,
        action,
        duration: isWaiting || job.last_error?.trim() ? Infinity : undefined,
      };

      if (isWaiting) {
        toast(`Job needs input: ${job.name}`, options);
      } else if (job.last_error?.trim()) {
        toast.error(`Job failed: ${job.name}`, options);
      } else {
        toast.success(`Job triggered: ${job.name}`, options);
      }

      if (voiceMode && detail.trim()) {
        // Best-effort hands-free read-out; ignore autoplay/synthesis failures.
        void play(toastId, detail).catch(() => {});
      }
    },
    [openJobDetail, play, voiceMode],
  );

  useJobEvents(handleJob);

  return null;
}
