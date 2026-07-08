'use client';

import { memo, useMemo, useState } from 'react';
import { usePathname } from 'next/navigation';
import { CircleAlert, Expand, Pin, PinOff } from 'lucide-react';
import { toast } from 'sonner';

import { PanelFrame } from '@/components/wotbot/chat-tool-calls/panel-frame';
import {
  DetailsToggle,
  ToolCardHeader,
} from '@/components/wotbot/chat-tool-calls/tool-card-shell';
import {
  enrichArtifactForPinning,
  normalizeWebInterfaceResult,
  type WebInterfaceArtifact,
} from '@/components/wotbot/chat-tool-calls/web-interface-model';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Collapsible, CollapsibleContent } from '@/components/ui/collapsible';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { pinPanel } from '@/lib/panels-api';

import {
  formatToolName,
  type CatchAllToolCallRenderProps,
} from '../chat-tool-call-model';

/** Self-contained framed interface with a fullscreen + pin affordance. */
export const WebInterfaceArtifactView = memo(function WebInterfaceArtifactView({
  artifact,
}: {
  artifact: WebInterfaceArtifact;
}) {
  const [isFullscreenOpen, setIsFullscreenOpen] = useState(false);
  const [isPinning, setIsPinning] = useState(false);
  const [pinned, setPinned] = useState(false);
  const pathname = usePathname();
  const src = `/api/artifacts/${encodeURIComponent(artifact.filename)}`;
  const canPin = typeof artifact.html === 'string' && artifact.html.length > 0;

  const handlePin = async () => {
    if (!artifact.html) {
      return;
    }
    setIsPinning(true);
    try {
      // Soft provenance: the current chat id from /chat/[id] (nullable).
      const chatMatch = pathname.match(/\/chat\/([^/]+)/);
      await pinPanel({
        title: artifact.title || 'Untitled panel',
        html: artifact.html,
        capabilities: artifact.capabilities,
        sourceThreadId: chatMatch ? chatMatch[1] : null,
      });
      setPinned(true);
      toast.success('Pinned to Panels');
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to pin panel',
      );
    } finally {
      setIsPinning(false);
    }
  };

  return (
    <Dialog open={isFullscreenOpen} onOpenChange={setIsFullscreenOpen}>
      <Card className="gap-0 border border-border/55 bg-background/45 py-0 shadow-none ring-0">
        <CardContent className="space-y-2 py-2">
          <div className="flex items-center justify-end gap-1 px-0.5">
            {canPin ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    aria-label="Pin to Panels"
                    className="text-muted-foreground hover:text-foreground"
                    disabled={isPinning || pinned}
                    onClick={() => void handlePin()}
                    size="icon-xs"
                    type="button"
                    variant="ghost"
                  >
                    {pinned ? (
                      <PinOff className="size-3.5" />
                    ) : (
                      <Pin className="size-3.5" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="top">
                  {pinned ? 'Pinned' : 'Pin to Panels'}
                </TooltipContent>
              </Tooltip>
            ) : null}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  aria-label="Open fullscreen interface"
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
          <PanelFrame
            capabilities={artifact.capabilities}
            src={src}
            title={`Interface ${artifact.ref}`}
          />
        </CardContent>
      </Card>

      {isFullscreenOpen ? (
        <DialogContent
          className="max-w-[min(96vw,90rem)] gap-0 p-0 sm:max-w-[min(96vw,90rem)]"
          showCloseButton
        >
          <DialogHeader className="border-b border-border/55 px-4 py-3 pr-12">
            <DialogTitle className="text-sm">Interactive interface</DialogTitle>
          </DialogHeader>
          <div className="overflow-auto p-4">
            <PanelFrame
              capabilities={artifact.capabilities}
              className="h-[78vh] rounded-xl"
              src={src}
              title={`Interface ${artifact.ref}`}
            />
          </div>
        </DialogContent>
      ) : null}
    </Dialog>
  );
});

export const WebInterfaceCard = memo(function WebInterfaceCard({
  args,
  result,
  showInterface = true,
  status,
}: CatchAllToolCallRenderProps & { showInterface?: boolean }) {
  const [showDetails, setShowDetails] = useState(false);

  const html = (args as { html?: string } | undefined)?.html ?? '';
  const parsed = useMemo(
    () => (status === 'complete' ? normalizeWebInterfaceResult(result) : {}),
    [status, result],
  );
  const artifact = parsed.artifact;
  const hasError = !!parsed.error;
  const isCompleted = status === 'complete';
  const summary =
    status === 'executing'
      ? 'Building interface'
      : hasError
        ? 'Failed to build interface'
        : artifact
          ? 'Interactive interface'
          : 'No interface produced';

  return (
    <Collapsible
      className="wotbot-tool-call space-y-2"
      open={showDetails}
      onOpenChange={setShowDetails}
    >
      <ToolCardHeader
        action={html ? <DetailsToggle expanded={showDetails} /> : undefined}
        hasError={hasError}
        isCompleted={isCompleted}
        status={status}
        summary={summary}
        title={formatToolName('create_web_interface')}
      />

      <CollapsibleContent className="data-closed:hidden">
        {html ? (
          <pre className="max-h-52 overflow-auto rounded-lg border border-border/55 bg-muted/20 px-3 py-2.5 text-[0.72rem] leading-5 whitespace-pre-wrap text-foreground">
            {html}
          </pre>
        ) : null}
      </CollapsibleContent>

      {status === 'executing' ? (
        <div className="px-0.5 text-[0.72rem] text-muted-foreground">
          Building interface…
        </div>
      ) : null}

      {hasError ? (
        <Alert
          className="border-destructive/25 bg-destructive/5"
          variant="destructive"
        >
          <CircleAlert className="h-4 w-4" />
          <AlertTitle>Interface failed</AlertTitle>
          <AlertDescription>
            <pre className="overflow-auto font-mono text-[0.72rem] leading-5 whitespace-pre-wrap text-destructive">
              {parsed.error}
            </pre>
          </AlertDescription>
        </Alert>
      ) : null}

      {showInterface && isCompleted && artifact ? (
        <WebInterfaceArtifactView
          artifact={enrichArtifactForPinning(artifact, args)}
        />
      ) : null}
    </Collapsible>
  );
});
