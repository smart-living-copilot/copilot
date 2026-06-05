'use client';

import { memo, useRef } from 'react';

import { useWotBridge } from '@/components/copilot/chat-tool-calls/use-wot-bridge';
import { type WotCapability } from '@/components/copilot/chat-tool-calls/web-interface-model';
import { cn } from '@/lib/utils';

/**
 * Sandboxed iframe for a generated WoT panel, wired to the capability-enforcing
 * postMessage bridge. Shared by ephemeral chat panels (src = artifact) and
 * pinned panels (src = panel render route).
 */
export const PanelFrame = memo(function PanelFrame({
  src,
  capabilities,
  title,
  className,
  interactive = true,
}: {
  src: string;
  capabilities: WotCapability[];
  title: string;
  className?: string;
  interactive?: boolean;
}) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  useWotBridge(iframeRef, capabilities, { enabled: interactive });

  return (
    <iframe
      ref={iframeRef}
      className={cn(
        'w-full rounded-lg border border-border/55 bg-background',
        className ?? 'h-[26rem]',
      )}
      // Untrusted, LLM-authored content: interactive frames get scripts only,
      // never allow-same-origin. Preview frames keep scripts disabled entirely.
      sandbox={interactive ? 'allow-scripts' : ''}
      src={src}
      title={title}
    />
  );
});
