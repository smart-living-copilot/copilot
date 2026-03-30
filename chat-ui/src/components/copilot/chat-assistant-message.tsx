'use client';

import {
  Markdown,
  type AssistantMessageProps,
  useChatContext,
} from '@copilotkit/react-ui';
import { useState } from 'react';
import { cn } from '@/lib/utils';

export function ChatAssistantMessage(props: AssistantMessageProps) {
  const { icons, labels } = useChatContext();
  const {
    feedback,
    isCurrentMessage,
    isLoading,
    markdownTagRenderers,
    message,
    onCopy,
    onRegenerate,
    onThumbsDown,
    onThumbsUp,
  } = props;
  const [copied, setCopied] = useState(false);

  const content = message?.content?.trim() ?? '';
  const hasContent = content.length > 0;
  const subComponent = message?.generativeUI?.() ?? props.subComponent;
  const subComponentPosition = message?.generativeUIPosition ?? 'after';
  const renderBefore = subComponent && subComponentPosition === 'before';
  const renderAfter = subComponent && subComponentPosition !== 'before';

  const handleCopy = () => {
    if (!hasContent) {
      return;
    }

    navigator.clipboard.writeText(content);
    setCopied(true);
    onCopy?.(content);
    window.setTimeout(() => setCopied(false), 2000);
  };

  const handleRegenerate = () => {
    onRegenerate?.();
  };

  const handleThumbsUp = () => {
    if (message) {
      onThumbsUp?.(message);
    }
  };

  const handleThumbsDown = () => {
    if (message) {
      onThumbsDown?.(message);
    }
  };

  return (
    <>
      {renderBefore ? <div className="mb-2">{subComponent}</div> : null}

      {hasContent ? (
        <div className="mb-3 space-y-2">
          <div className="copilotKitMessage copilotKitAssistantMessage">
            <Markdown content={content} components={markdownTagRenderers} />
          </div>

          {!isLoading ? (
            <div
              className={cn(
                'flex items-center gap-2 pl-0.5',
                isCurrentMessage && 'opacity-100',
              )}
            >
              {onRegenerate ? (
                <button
                  className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/60 hover:text-primary"
                  aria-label={labels.regenerateResponse}
                  onClick={handleRegenerate}
                  title={labels.regenerateResponse}
                  type="button"
                >
                  {icons.regenerateIcon}
                </button>
              ) : null}

              <button
                className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/60 hover:text-primary"
                aria-label={labels.copyToClipboard}
                onClick={handleCopy}
                title={labels.copyToClipboard}
                type="button"
              >
                {copied ? (
                  <span className="text-[10px] font-bold">✓</span>
                ) : (
                  icons.copyIcon
                )}
              </button>

              {onThumbsUp ? (
                <button
                  className={cn(
                    'inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/60 hover:text-primary',
                    feedback === 'thumbsUp' &&
                      'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground',
                  )}
                  aria-label={labels.thumbsUp}
                  onClick={handleThumbsUp}
                  title={labels.thumbsUp}
                  type="button"
                >
                  {icons.thumbsUpIcon}
                </button>
              ) : null}

              {onThumbsDown ? (
                <button
                  className={cn(
                    'inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/60 hover:text-primary',
                    feedback === 'thumbsDown' &&
                      'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground',
                  )}
                  aria-label={labels.thumbsDown}
                  onClick={handleThumbsDown}
                  title={labels.thumbsDown}
                  type="button"
                >
                  {icons.thumbsDownIcon}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {renderAfter ? <div className="mb-2">{subComponent}</div> : null}
      {isLoading ? <span>{icons.activityIcon}</span> : null}
    </>
  );
}
