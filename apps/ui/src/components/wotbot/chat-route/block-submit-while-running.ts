import type { KeyboardEvent } from 'react';

/**
 * Returns a capture-phase key handler that swallows plain Enter while the agent
 * is running. This stops the keystroke before CopilotChatInput's own handler
 * runs, so it neither submits a new prompt nor aborts the in-flight run.
 * Shift+Enter still falls through to insert a newline.
 */
export function blockSubmitWhileRunning(isRunning?: boolean) {
  return (event: KeyboardEvent<HTMLDivElement>) => {
    if (isRunning && event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      event.stopPropagation();
    }
  };
}
