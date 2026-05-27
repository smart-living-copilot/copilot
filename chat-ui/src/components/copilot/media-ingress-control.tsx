'use client';

import { AudioLines, LoaderCircle, PhoneOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { MediaIngressSession } from '@/hooks/use-media-ingress-session';

export function MediaIngressControl({
  session,
}: {
  session: MediaIngressSession;
}) {
  const isBusy =
    session.state === 'requesting' || session.state === 'connecting';
  const isActive = session.state === 'connected';
  const isErrored = session.state === 'error';
  const label = isActive
    ? 'Stop voice and video'
    : isBusy
      ? 'Connecting'
      : isErrored
        ? 'Retry voice and video'
        : 'Start voice and video';

  return (
    <div className="flex min-w-0 items-center gap-2">
      <Button
        aria-label={label}
        aria-pressed={isActive}
        disabled={isBusy}
        onClick={() => (isActive ? session.stop() : void session.start())}
        size="icon"
        title={label}
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
      </Button>
    </div>
  );
}
