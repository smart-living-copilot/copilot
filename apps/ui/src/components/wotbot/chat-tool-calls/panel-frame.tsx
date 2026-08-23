'use client';

import { memo, useRef } from 'react';

import { useWotBridge } from '@/components/wotbot/chat-tool-calls/use-wot-bridge';
import { type WotCapability } from '@/components/wotbot/chat-tool-calls/web-interface-model';
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
      // Untrusted, LLM-authored content. `allow-same-origin` is safe here only
      // because `src` points at the panel's own origin (see `panel-origin.ts`):
      // it means "your own origin", which is cross-origin to the app. Without
      // it the frame would be opaque-origin and denied every permission-gated
      // API. Preview frames keep scripts disabled entirely.
      allow={interactive ? 'camera; microphone' : ''}
      sandbox={interactive ? 'allow-scripts allow-same-origin' : ''}
      src={src}
      title={title}
    />
  );
});
