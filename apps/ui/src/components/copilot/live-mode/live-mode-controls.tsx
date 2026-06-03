import { Mic, MicOff, RotateCcw, Video, VideoOff, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { type MediaIngressSession } from '@/hooks/use-media-ingress-session';

function ShortcutKey({ children }: { children: string }) {
  return (
    <kbd className="rounded border border-border/60 bg-background/50 px-1 text-[0.65rem] font-medium">
      {children}
    </kbd>
  );
}

export function LiveModeControls({
  mediaControlsDisabled,
  session,
}: {
  mediaControlsDisabled: boolean;
  session: MediaIngressSession;
}) {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-6 z-20 flex justify-center px-4">
      <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-border bg-background/85 px-3 py-2 shadow-lg backdrop-blur">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              aria-label={
                session.isMicrophoneMuted
                  ? 'Unmute microphone'
                  : 'Mute microphone'
              }
              aria-pressed={session.isMicrophoneMuted}
              className="rounded-full"
              disabled={mediaControlsDisabled}
              onClick={() =>
                session.setMicrophoneMuted(!session.isMicrophoneMuted)
              }
              size="icon-lg"
              type="button"
              variant={session.isMicrophoneMuted ? 'secondary' : 'outline'}
            >
              {session.isMicrophoneMuted ? (
                <MicOff className="size-4" />
              ) : (
                <Mic className="size-4" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent className="flex items-center gap-2" side="top">
            {session.isMicrophoneMuted
              ? 'Unmute microphone'
              : 'Mute microphone'}
            <ShortcutKey>M</ShortcutKey>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              aria-label={
                session.isCameraEnabled ? 'Turn camera off' : 'Turn camera on'
              }
              aria-pressed={!session.isCameraEnabled}
              className="rounded-full"
              disabled={mediaControlsDisabled}
              onClick={() => session.setCameraEnabled(!session.isCameraEnabled)}
              size="icon-lg"
              type="button"
              variant={session.isCameraEnabled ? 'outline' : 'secondary'}
            >
              {session.isCameraEnabled ? (
                <Video className="size-4" />
              ) : (
                <VideoOff className="size-4" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent className="flex items-center gap-2" side="top">
            {session.isCameraEnabled ? 'Turn camera off' : 'Turn camera on'}
            <ShortcutKey>V</ShortcutKey>
          </TooltipContent>
        </Tooltip>

        {session.state === 'error' ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                aria-label="Try again"
                className="rounded-full"
                onClick={() => void session.start()}
                size="icon-lg"
                type="button"
                variant="default"
              >
                <RotateCcw className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top">Try again</TooltipContent>
          </Tooltip>
        ) : null}

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              aria-label={
                session.state === 'error' ? 'Back to chat' : 'Exit live mode'
              }
              className="rounded-full"
              onClick={session.stop}
              size="icon-lg"
              type="button"
              variant="outline"
            >
              <X className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top">
            {session.state === 'error' ? 'Back to chat' : 'Exit live mode'}
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}

export { ShortcutKey };
