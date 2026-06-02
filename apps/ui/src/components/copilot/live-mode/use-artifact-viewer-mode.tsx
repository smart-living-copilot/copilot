import { ImageIcon, LineChart } from 'lucide-react';
import { useCallback, useMemo, useState, type ReactNode } from 'react';

import type { RunCodeArtifact } from '@/components/copilot/chat-tool-call-model';

type ReopenChipInfo = { icon: ReactNode; label: string };

type ArtifactViewerMode = {
  inViewer: boolean;
  dismissViewer: () => void;
  reopenViewer: () => void;
  showReopenChip: boolean;
  reopenChipInfo: ReopenChipInfo | null;
};

export function useArtifactViewerMode({
  artifacts,
  latestAssistantText,
  latestUserTranscript,
}: {
  artifacts: RunCodeArtifact[];
  latestAssistantText: string | null;
  latestUserTranscript: string | null;
}): ArtifactViewerMode {
  const artifactSignature = useMemo(
    () =>
      artifacts
        .map((artifact) => `${artifact.kind}:${artifact.filename}`)
        .join('|'),
    [artifacts],
  );
  const hasArtifact = !!artifactSignature && !!latestAssistantText;
  const [trackedSignature, setTrackedSignature] = useState<string | null>(null);
  const [transcriptAtArrival, setTranscriptAtArrival] = useState<string | null>(
    null,
  );
  const [manuallyDismissedSignature, setManuallyDismissedSignature] = useState<
    string | null
  >(null);
  const nextTrackedSignature = hasArtifact ? artifactSignature : null;
  if (nextTrackedSignature !== trackedSignature) {
    setTrackedSignature(nextTrackedSignature);
    setTranscriptAtArrival(nextTrackedSignature ? latestUserTranscript : null);
  }

  const transcriptAdvanced =
    hasArtifact && latestUserTranscript !== transcriptAtArrival;
  const inViewer =
    hasArtifact &&
    !transcriptAdvanced &&
    artifactSignature !== manuallyDismissedSignature;

  const dismissViewer = useCallback(() => {
    setManuallyDismissedSignature(artifactSignature);
  }, [artifactSignature]);

  const reopenViewer = useCallback(() => {
    setManuallyDismissedSignature(null);
    setTranscriptAtArrival(latestUserTranscript);
  }, [latestUserTranscript]);

  const showReopenChip = hasArtifact && !inViewer;
  const reopenChipInfo = useMemo<ReopenChipInfo | null>(() => {
    if (artifacts.length === 0) return null;
    const onlyImages = artifacts.every((artifact) => artifact.kind === 'image');
    const noun = onlyImages
      ? artifacts.length > 1
        ? 'images'
        : 'image'
      : artifacts.length > 1
        ? 'charts'
        : 'chart';
    return {
      icon: onlyImages ? (
        <ImageIcon className="size-4" />
      ) : (
        <LineChart className="size-4" />
      ),
      label: `View ${artifacts.length > 1 ? `${artifacts.length} ` : ''}${noun}`,
    };
  }, [artifacts]);

  return {
    inViewer,
    dismissViewer,
    reopenViewer,
    showReopenChip,
    reopenChipInfo,
  };
}
