'use client';

import { useEffect } from 'react';
import { RefreshCw } from 'lucide-react';

import { ErrorState } from '@/components/error-state';
import { Button } from '@/components/ui/button';

/**
 * Segment-level boundary: keeps a failed page from taking down the whole app.
 *
 * Without this, any render throw unmounts the React root and leaves a blank
 * document with no way back. That is not hypothetical here -- assistant-ui's
 * store selectors run inside `useSyncExternalStore`'s `getSnapshot`, where a
 * throw tears down the root, and the chat is the busiest code in the app.
 */
export default function RouteError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    // No error service is wired up; the console is what a developer has.
    console.error('Route error boundary caught:', error);
  }, [error]);

  return (
    <ErrorState
      action={
        <Button onClick={() => unstable_retry()} type="button">
          <RefreshCw className="size-4" />
          Try again
        </Button>
      }
      description="This page hit an unexpected error. Retrying re-runs it; the rest of the app is still usable."
      detail={error.digest ? `Digest ${error.digest}` : error.message}
      title="Something went wrong"
    />
  );
}
