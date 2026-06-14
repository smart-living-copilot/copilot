'use client';

import { useEffect, useRef } from 'react';

import { type JobRecord } from '@/lib/jobs-api';

type JobEventHandler = (job: JobRecord) => void;

type JobRunEvent = {
  job?: JobRecord;
};

interface UseJobEventsOptions {
  enabled?: boolean;
}

/**
 * Subscribe to the job run event stream (`/api/jobs/events`) and invoke
 * `onJob` with the updated job record for every event. Uses the browser
 * `EventSource` when available, falling back to a streamed `fetch` reader.
 *
 * The handler is held in a ref so the subscription is established once and is
 * not torn down when the caller passes a new closure on each render.
 */
export function useJobEvents(
  onJob: JobEventHandler,
  { enabled = true }: UseJobEventsOptions = {},
): void {
  const handlerRef = useRef(onJob);
  handlerRef.current = onJob;

  useEffect(() => {
    if (!enabled) {
      return;
    }

    let active = true;
    let cleanup: (() => void) | null = null;

    const handleMessage = (raw: string) => {
      let payload: JobRunEvent;
      try {
        payload = JSON.parse(raw) as JobRunEvent;
      } catch {
        return;
      }
      if (payload.job) {
        handlerRef.current(payload.job);
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
  }, [enabled]);
}
