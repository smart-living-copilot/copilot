'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { useWotBridge } from '@/components/wotbot/chat-tool-calls/use-wot-bridge';
import { type WotCapability } from '@/components/wotbot/chat-tool-calls/web-interface-model';

/**
 * Opens a panel as a page of its own, still wired to the device bridge.
 *
 * A panel has its own origin now, so it works as a top-level page -- but the
 * bridge is postMessage between two windows, and the opener is the only handle
 * the panel has once it is not framed. `wot_bridge.js` falls back to
 * `window.opener` for exactly this, so the tab that opened it stays the host and
 * keeps enforcing the capability allowlist.
 *
 * Consequences worth knowing: the opening tab must stay open, and the popup
 * cannot be opened with `noopener` -- that is the channel.
 */
export function usePanelPopup(src: string, capabilities: WotCapability[]) {
  const popupRef = useRef<Window | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const origin = (() => {
    try {
      return new URL(src, window.location.href).origin;
    } catch {
      return undefined;
    }
  })();

  useWotBridge(popupRef, capabilities, { enabled: isOpen, origin });

  // The popup can be closed from its own tab, which fires no event here.
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const timer = window.setInterval(() => {
      if (popupRef.current?.closed !== false) {
        popupRef.current = null;
        setIsOpen(false);
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isOpen]);

  useEffect(() => () => popupRef.current?.close(), []);

  const open = useCallback(() => {
    const existing = popupRef.current;
    if (existing && !existing.closed) {
      existing.focus();
      return true;
    }
    // Deliberately without 'noopener': the opener reference is the bridge.
    const popup = window.open(src, '_blank');
    popupRef.current = popup;
    setIsOpen(Boolean(popup));
    return Boolean(popup);
  }, [src]);

  return { isOpen, open };
}
