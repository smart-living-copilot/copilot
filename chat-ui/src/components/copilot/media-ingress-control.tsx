'use client';

import { AudioLines, LoaderCircle, PhoneOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { MediaIngressSession } from '@/hooks/use-media-ingress-session';

export function MediaIngressControl({
  session,
  compact = false,
}: {
  session: MediaIngressSession;
  compact?: boolean;
}) {
  const isBusy =
    session.state === 'requesting' || session.state === 'connecting';
  const isActive = session.state === 'connected';
  const isErrored = session.state === 'error';
  const label = isBusy
    ? 'Connecting'
    : isActive
      ? 'Live'
      : isErrored
        ? 'Retry live'
        : 'Voice/video';

  return (
    <div className="flex min-w-0 items-center gap-2">
      <Button
        aria-pressed={isActive}
        disabled={isBusy}
        onClick={() => (isActive ? session.stop() : void session.start())}
        size={compact ? 'icon' : 'sm'}
        title={isActive ? 'Stop voice and video' : 'Start voice and video'}
        type="button"
        variant={isActive ? 'secondary' : 'outline'}
      >
        {isBusy ? (
          <LoaderCircle className="size-4 animate-spin" />
        ) : isActive ? (
          <PhoneOff className="size-4" />
        ) : (
          <AudioLines className="size-4" />
        )}
        {compact ? null : <span className="hidden sm:inline">{label}</span>}
      </Button>
      {!compact && session.error ? (
        <span className="hidden max-w-48 truncate text-xs text-destructive lg:inline">
          {session.error}
        </span>
      ) : null}
    </div>
  );
}
