'use client';

import { useEffect } from 'react';

const DEFAULT_UNSAVED_MESSAGE =
  'You have unsaved changes. Leave without saving?';

function isPlainNavigationClick(event: MouseEvent) {
  return (
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  );
}

function getAnchorFromEvent(event: MouseEvent) {
  if (!(event.target instanceof Element)) {
    return null;
  }

  return event.target.closest<HTMLAnchorElement>('a[href]');
}

function shouldGuardAnchorNavigation(anchor: HTMLAnchorElement) {
  const rawHref = anchor.getAttribute('href');
  if (
    !rawHref ||
    rawHref.startsWith('#') ||
    anchor.hasAttribute('download') ||
    (anchor.target && anchor.target !== '_self')
  ) {
    return false;
  }

  const nextUrl = new URL(anchor.href, window.location.href);
  return nextUrl.href !== window.location.href;
}

export function useUnsavedChangesGuard(
  enabled: boolean,
  message = DEFAULT_UNSAVED_MESSAGE,
) {
  useEffect(() => {
    if (!enabled) {
      return;
    }

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = message;
      return message;
    };

    const handleDocumentClick = (event: MouseEvent) => {
      if (event.defaultPrevented || !isPlainNavigationClick(event)) {
        return;
      }

      const anchor = getAnchorFromEvent(event);
      if (!anchor || !shouldGuardAnchorNavigation(anchor)) {
        return;
      }

      if (!window.confirm(message)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    document.addEventListener('click', handleDocumentClick, true);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      document.removeEventListener('click', handleDocumentClick, true);
    };
  }, [enabled, message]);
}
