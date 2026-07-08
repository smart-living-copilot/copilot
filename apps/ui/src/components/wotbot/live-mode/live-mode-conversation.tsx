import { type ReactNode } from 'react';

import {
  AssistantThinkingDots,
  LiveResponseMarkdown,
} from '@/components/wotbot/live-mode/live-response-markdown';
import { MediaStreamAura } from '@/components/wotbot/media-stream-aura';
import { Button } from '@/components/ui/button';
import { type MediaIngressSession } from '@/hooks/use-media-ingress-session';

interface ReopenChipInfo {
  icon: ReactNode;
  label: string;
}

interface LiveModeStatus {
  detail: string;
  icon: ReactNode;
}

export function LiveModeConversation({
  hasAnyContent,
  reopenChipInfo,
  reopenViewer,
  session,
  showAssistantPending,
  showReopenChip,
  status,
}: {
  hasAnyContent: boolean;
  reopenChipInfo: ReopenChipInfo | null;
  reopenViewer: () => void;
  session: MediaIngressSession;
  showAssistantPending: boolean;
  showReopenChip: boolean;
  status: LiveModeStatus;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto px-6 pb-36 pt-16 text-center">
      <MediaStreamAura
        icon={status.icon}
        size={hasAnyContent ? 'md' : 'lg'}
        state={session.state}
        stream={session.localStream}
      />

      {!hasAnyContent ? (
        <p className="mt-6 max-w-md text-balance text-sm font-medium text-muted-foreground md:text-base">
          {status.detail}
        </p>
      ) : null}

      <div className="mt-8 w-full max-w-2xl space-y-6">
        {session.latestUserTranscript ? (
          <div className="text-left">
            <div className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              You said
            </div>
            <p className="text-base italic leading-7 text-muted-foreground md:text-lg">
              &ldquo;{session.latestUserTranscript}&rdquo;
            </p>
          </div>
        ) : null}

        {showReopenChip && reopenChipInfo ? (
          <div className="flex justify-start">
            <Button
              className="gap-2"
              onClick={reopenViewer}
              size="sm"
              type="button"
              variant="outline"
            >
              {reopenChipInfo.icon}
              {reopenChipInfo.label}
            </Button>
          </div>
        ) : null}

        {session.latestAssistantText ? (
          <LiveResponseMarkdown text={session.latestAssistantText} />
        ) : null}

        {showAssistantPending ? <AssistantThinkingDots /> : null}
      </div>
    </div>
  );
}
