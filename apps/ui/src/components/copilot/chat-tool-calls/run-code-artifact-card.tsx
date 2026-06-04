'use client';

import { memo, useState } from 'react';
import { Expand } from 'lucide-react';

import { ArtifactPreview } from '@/components/copilot/chat-tool-calls/artifact-preview';
import { DetailsToggle } from '@/components/copilot/chat-tool-calls/tool-card-shell';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Collapsible, CollapsibleContent } from '@/components/ui/collapsible';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import { type RunCodeArtifact } from '../chat-tool-call-model';

export const RunCodeArtifactCard = memo(function RunCodeArtifactCard({
  artifact,
}: {
  artifact: RunCodeArtifact;
}) {
  const [isFullscreenOpen, setIsFullscreenOpen] = useState(false);
  const [showPreview, setShowPreview] = useState(true);
  const artifactType =
    artifact.kind === 'plotly' ? 'Interactive chart' : 'Generated image';

  return (
    <Dialog open={isFullscreenOpen} onOpenChange={setIsFullscreenOpen}>
      <Collapsible open={showPreview} onOpenChange={setShowPreview}>
        <Card className="gap-0 border border-border/55 bg-background/45 py-0 shadow-none ring-0">
          <CardContent className="space-y-2 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2 px-0.5">
                <Badge
                  className="h-5 font-mono text-[0.66rem]"
                  variant="outline"
                >
                  {artifact.ref}
                </Badge>
                <span className="truncate text-[0.7rem] text-muted-foreground">
                  {artifactType}
                </span>
              </div>

              <div className="flex items-center gap-1">
                <DetailsToggle expanded={showPreview} />

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      aria-label="Open fullscreen preview"
                      className="text-muted-foreground hover:text-foreground"
                      onClick={() => setIsFullscreenOpen(true)}
                      size="icon-xs"
                      type="button"
                      variant="ghost"
                    >
                      <Expand className="size-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top">Open fullscreen</TooltipContent>
                </Tooltip>
              </div>
            </div>

            <CollapsibleContent className="data-closed:hidden">
              <ArtifactPreview artifact={artifact} />
            </CollapsibleContent>
          </CardContent>
        </Card>

        {isFullscreenOpen ? (
          <DialogContent
            className="max-w-[min(96vw,90rem)] gap-0 p-0 sm:max-w-[min(96vw,90rem)]"
            showCloseButton
          >
            <DialogHeader className="border-b border-border/55 px-4 py-3 pr-12">
              <DialogTitle className="flex items-center gap-2 text-sm">
                <Badge
                  className="h-5 font-mono text-[0.66rem]"
                  variant="outline"
                >
                  {artifact.ref}
                </Badge>
                <span>{artifactType}</span>
              </DialogTitle>
              <DialogDescription className="text-[0.72rem]">
                Fullscreen preview for {artifact.filename}
              </DialogDescription>
            </DialogHeader>

            <div className="overflow-auto p-4">
              <ArtifactPreview artifact={artifact} fullscreen />
            </div>
          </DialogContent>
        ) : null}
      </Collapsible>
    </Dialog>
  );
});
