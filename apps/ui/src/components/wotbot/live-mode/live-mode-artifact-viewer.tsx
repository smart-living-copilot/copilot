import { ArtifactPreview } from '@/components/wotbot/chat-tool-call-cards';
import type { RunCodeArtifact } from '@/components/wotbot/chat-tool-call-model';

export function LiveModeArtifactViewer({
  artifacts,
}: {
  artifacts: RunCodeArtifact[];
}) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center px-4 pb-28 pt-14 md:px-8">
      {artifacts.length === 1 ? (
        <ArtifactPreview artifact={artifacts[0]} fill />
      ) : (
        <div className="grid h-full w-full max-w-6xl grid-cols-1 gap-3 sm:grid-cols-2">
          {artifacts.map((artifact) => (
            <div
              className="min-h-0 overflow-hidden rounded-xl border border-border bg-background/70 p-2 shadow-sm"
              key={`${artifact.kind}:${artifact.filename}`}
            >
              <ArtifactPreview artifact={artifact} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
