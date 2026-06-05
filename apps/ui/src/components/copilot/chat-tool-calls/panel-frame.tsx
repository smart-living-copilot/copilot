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
}: {
  src: string;
  capabilities: WotCapability[];
  title: string;
  className?: string;
}) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  // Enforces the capability allowlist and bridges runtime calls for this frame.
  useWotBridge(iframeRef, capabilities);

  return (
    <iframe
      ref={iframeRef}
      className={cn(
        'w-full rounded-lg border border-border/55 bg-background',
        className ?? 'h-[26rem]',
      )}
      // Untrusted, LLM-authored content: scripts only, NO allow-same-origin, so
      // the document runs in an opaque origin with no cookies/credentialed fetch.
      sandbox="allow-scripts"
      src={src}
      title={title}
    />
  );
});
