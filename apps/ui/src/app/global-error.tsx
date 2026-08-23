'use client';

import { useEffect } from 'react';

import './globals.css';

/**
 * Last-resort boundary for failures in the root layout itself.
 *
 * It replaces the whole document, so it brings its own `html`/`body` and cannot
 * rely on anything the layout sets up -- no providers, no theme, no fonts. The
 * markup is intentionally dependency-free for that reason.
 */
export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error('Global error boundary caught:', error);
  }, [error]);

  return (
    <html lang="en">
      <body className="bg-background text-foreground">
        <div className="flex min-h-svh flex-col items-center justify-center gap-4 px-6 text-center">
          <div className="max-w-md space-y-2">
            <h1 className="text-xl font-semibold tracking-tight">
              WoTBot could not start
            </h1>
            <p className="text-sm text-muted-foreground">
              The application shell failed to render. Reloading usually clears
              it.
            </p>
            {error.digest ? (
              <p className="font-mono text-xs text-muted-foreground/80">
                Digest {error.digest}
              </p>
            ) : null}
          </div>

          <button
            className="cursor-pointer rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            onClick={() => unstable_retry()}
            type="button"
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
