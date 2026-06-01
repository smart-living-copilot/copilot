'use client';

import { useEffect, useRef } from 'react';
import { toast } from 'sonner';

import { useJobDetail } from '@/components/jobs/job-detail-context';
import { type JobRecord } from '@/lib/jobs-api';

type JobRunEvent = {
  job: JobRecord;
};

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

  useEffect(() => {
    let active = true;
    let cleanup: (() => void) | null = null;

    const handleMessage = (raw: string) => {
      let payload: JobRunEvent;
      try {
        payload = JSON.parse(raw) as JobRunEvent;
      } catch {
        return;
      }

      const job = payload.job;
      if (!job) {
        return;
      }

      const runKey = `${job.id}:${job.run_count}:${job.last_run_at ?? ''}`;
      if (seenRunsRef.current.has(runKey)) {
        return;
      }
      seenRunsRef.current.add(runKey);

      const detail = summarizeResult(job);
      if (job.last_error?.trim()) {
        toast.error(`Job failed: ${job.name}`, {
          description: (
            <button
              type="button"
              className="w-full cursor-pointer text-left"
              onClick={() => openJobDetail(job.id)}
            >
              {detail}
            </button>
          ),
          action: {
            label: 'View details',
            onClick: () => openJobDetail(job.id),
          },
        });
      } else {
        toast.success(`Job triggered: ${job.name}`, {
          description: (
            <button
              type="button"
              className="w-full cursor-pointer text-left"
              onClick={() => openJobDetail(job.id)}
            >
              {detail}
            </button>
          ),
          action: {
            label: 'View details',
            onClick: () => openJobDetail(job.id),
          },
        });
      }
    };

    const subscribeWithEventSource = () => {
      const source = new EventSource('/api/jobs/events');
      source.onmessage = (message: MessageEvent<string>) => {
        handleMessage(message.data);
      };
      source.onerror = () => {
        source.close();
      };
      return () => source.close();
    };

    const subscribeWithFetch = () => {
      const controller = new AbortController();

      const connect = async () => {
        while (active) {
          try {
            const res = await fetch('/api/jobs/events', {
              method: 'GET',
              cache: 'no-store',
              headers: { Accept: 'text/event-stream' },
              signal: controller.signal,
            });

            const eventsUnavailable =
              res.status === 204 ||
              res.status === 404 ||
              res.status === 501 ||
              res.headers.get('x-jobs-events-unavailable') === '1';
            if (eventsUnavailable) {
              break;
            }

            if (!res.ok || !res.body) {
              throw new Error(`SSE fetch failed (${res.status})`);
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (active) {
              const { done, value } = await reader.read();
              if (done) {
                break;
              }

              buffer += decoder.decode(value, { stream: true });
              const frames = buffer.split('\n\n');
              buffer = frames.pop() ?? '';

              for (const frame of frames) {
                const dataLines = frame
                  .split('\n')
                  .filter((line) => line.startsWith('data:'))
                  .map((line) => line.slice(5).trimStart());

                if (!dataLines.length) {
                  continue;
                }
                handleMessage(dataLines.join('\n'));
              }
            }
          } catch {
            if (!active) {
              break;
            }
          }

          if (!active) {
            break;
          }
          await new Promise((resolve) => window.setTimeout(resolve, 3000));
        }
      };

      void connect();
      return () => controller.abort();
    };

    if (
      typeof window !== 'undefined' &&
      typeof window.EventSource !== 'undefined'
    ) {
      cleanup = subscribeWithEventSource();
    } else {
      cleanup = subscribeWithFetch();
    }

    return () => {
      active = false;
      cleanup?.();
    };
  }, [openJobDetail]);

  return null;
}
