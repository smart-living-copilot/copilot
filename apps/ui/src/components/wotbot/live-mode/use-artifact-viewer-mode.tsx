import { ImageIcon, LineChart, PanelsTopLeft } from 'lucide-react';
import { useCallback, useMemo, useState, type ReactNode } from 'react';

import type { LiveModeArtifact } from '@/components/wotbot/assistant/artifacts';

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
  artifacts: LiveModeArtifact[];
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
    const onlyPanels = artifacts.every((artifact) => artifact.kind === 'web');
    const noun = onlyImages
      ? artifacts.length > 1
        ? 'images'
        : 'image'
      : onlyPanels
        ? artifacts.length > 1
          ? 'panels'
          : 'panel'
        : artifacts.every((artifact) => artifact.kind === 'plotly')
          ? artifacts.length > 1
            ? 'charts'
            : 'chart'
          : 'results';
    return {
      icon: onlyImages ? (
        <ImageIcon className="size-4" />
      ) : onlyPanels ? (
        <PanelsTopLeft className="size-4" />
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
