'use client';

import {
  ArrowLeft,
  AudioLines,
  LoaderCircle,
  MicOff,
  Video,
} from 'lucide-react';
import { useMemo } from 'react';

import { LiveModeArtifactViewer } from '@/components/copilot/live-mode/live-mode-artifact-viewer';
import { LiveModeAudioElements } from '@/components/copilot/live-mode/live-mode-audio-elements';
import { LiveModeCameraPreview } from '@/components/copilot/live-mode/live-mode-camera-preview';
import {
  LiveModeControls,
  ShortcutKey,
} from '@/components/copilot/live-mode/live-mode-controls';
import { LiveModeConversation } from '@/components/copilot/live-mode/live-mode-conversation';
import { useArtifactViewerMode } from '@/components/copilot/live-mode/use-artifact-viewer-mode';
import { useLiveModeKeyboardShortcuts } from '@/components/copilot/live-mode/use-live-mode-keyboard-shortcuts';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { MediaIngressSession } from '@/hooks/use-media-ingress-session';
import type { RunCodeArtifact } from './chat-tool-call-model';

export function LiveModePanel({
  artifacts = [],
  session,
}: {
  artifacts?: RunCodeArtifact[];
  session: MediaIngressSession;
}) {
  const status = useMemo(() => {
    if (session.state === 'requesting') {
      return {
        detail: 'Waiting for camera and microphone access',
        icon: <LoaderCircle className="size-5 animate-spin" />,
      };
    }
    if (session.state === 'connecting') {
      return {
        detail: 'Opening the live media channel',
        icon: <LoaderCircle className="size-5 animate-spin" />,
      };
    }
    if (session.state === 'error') {
      return {
        detail: session.error || 'The live media channel could not be opened',
        icon: <Video className="size-5" />,
      };
    }
    if (session.isMicrophoneMuted) {
      return {
        detail: 'Microphone is off',
        icon: <MicOff className="size-5" />,
      };
    }
    return {
      detail: 'Ready when you are',
      icon: <AudioLines className="size-5" />,
    };
  }, [session.error, session.isMicrophoneMuted, session.state]);

  const mediaControlsDisabled =
    !session.localStream ||
    session.state === 'requesting' ||
    session.state === 'error';
  const {
    inViewer,
    dismissViewer,
    reopenViewer,
    showReopenChip,
    reopenChipInfo,
  } = useArtifactViewerMode({
    artifacts,
    latestAssistantText: session.latestAssistantText,
    latestUserTranscript: session.latestUserTranscript,
  });

  const isConnected = session.state === 'connected';
  const { setMicrophoneMuted, setCameraEnabled } = session;
  const isMicrophoneMuted = session.isMicrophoneMuted;
  const isCameraEnabled = session.isCameraEnabled;
  const showAssistantPending =
    session.isAssistantResponsePending && !session.latestAssistantText;

  useLiveModeKeyboardShortcuts({
    dismissViewer,
    inViewer,
    isCameraEnabled,
    isConnected,
    isMicrophoneMuted,
    mediaControlsDisabled,
    setCameraEnabled,
    setMicrophoneMuted,
  });

  const hasAnyContent =
    !!session.latestAssistantText ||
    !!session.latestUserTranscript ||
    showAssistantPending;

  return (
    <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
      <LiveModeAudioElements
        cameraSnapshotCueSeq={session.cameraSnapshotCueSeq}
        isConnected={isConnected}
        remoteStream={session.remoteStream}
      />

      {inViewer ? (
        <LiveModeArtifactViewer artifacts={artifacts} />
      ) : (
        <LiveModeConversation
          hasAnyContent={hasAnyContent}
          reopenChipInfo={reopenChipInfo}
          reopenViewer={reopenViewer}
          session={session}
          showAssistantPending={showAssistantPending}
          showReopenChip={showReopenChip}
          status={status}
        />
      )}

      <LiveModeCameraPreview
        inViewer={inViewer}
        isCameraEnabled={session.isCameraEnabled}
        localStream={session.localStream}
      />

      {inViewer ? (
        <div className="absolute left-3 top-3 z-20 md:left-4 md:top-4">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                aria-label="Back to conversation"
                className="rounded-full bg-background/85 shadow-sm backdrop-blur"
                onClick={dismissViewer}
                size="icon"
                type="button"
                variant="outline"
              >
                <ArrowLeft className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent className="flex items-center gap-2" side="right">
              Back to conversation
              <ShortcutKey>Esc</ShortcutKey>
            </TooltipContent>
          </Tooltip>
        </div>
      ) : null}

      <LiveModeControls
        mediaControlsDisabled={mediaControlsDisabled}
        session={session}
      />
    </section>
  );
}
