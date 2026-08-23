import Link from 'next/link';
import { CircleAlert, type LucideIcon } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * The shared full-page fallback for a route that failed or does not exist.
 *
 * Kept deliberately plain: it renders in place of a page whose own components
 * have already thrown once, so it depends on nothing beyond the design tokens.
 * It notably does not use `AppShell` -- if the shell is what failed, rendering
 * it again here would throw straight back out to the parent boundary.
 */
export function ErrorState({
  action,
  className,
  description,
  detail,
  icon: Icon = CircleAlert,
  title,
}: {
  action?: React.ReactNode;
  className?: string;
  description: string;
  /** Technical context (a digest, a message); shown quietly under the copy. */
  detail?: string;
  icon?: LucideIcon;
  title: string;
}) {
  return (
    <div
      className={cn(
        'flex h-full min-h-svh flex-col items-center justify-center gap-4 overflow-y-auto px-6 py-10 text-center',
        className,
      )}
    >
      <Icon className="size-8 text-muted-foreground" />

      <div className="max-w-md space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
        {/* Clamped: an unbounded message would push the actions out of a
            viewport that cannot scroll to reach them. */}
        {detail ? (
          <p className="line-clamp-6 font-mono text-xs break-all text-muted-foreground/80">
            {detail}
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center justify-center gap-2">
        {action}
        <Button asChild variant="outline">
          <Link href="/chat">Back to chat</Link>
        </Button>
      </div>
    </div>
  );
}
