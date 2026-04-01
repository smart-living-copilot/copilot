'use client';

import {
  Markdown,
  type AssistantMessageProps,
  useChatContext,
} from '@copilotkit/react-ui';
import { type ReactNode, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

function MessageActionButton({
  children,
  disabled = false,
  label,
  onClick,
}: {
  children: ReactNode;
  disabled?: boolean;
  label: string;
  onClick: () => void;
}) {
  const button = (
    <Button
      aria-label={label}
      className="text-muted-foreground hover:text-primary"
      disabled={disabled}
      onClick={onClick}
      size="icon-sm"
      type="button"
      variant="ghost"
    >
      {children}
    </Button>
  );

  if (disabled) {
    return button;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="top">{label}</TooltipContent>
    </Tooltip>
  );
}

export function ChatAssistantMessage(props: AssistantMessageProps) {
  const { icons, labels } = useChatContext();
  const { isCurrentMessage, isLoading, markdownTagRenderers, message, onCopy } =
    props;
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
              <MessageActionButton
                disabled={!hasContent}
                label={copied ? 'Copied' : labels.copyToClipboard}
                onClick={handleCopy}
              >
                {copied ? (
                  <span className="text-[10px] font-bold">✓</span>
                ) : (
                  icons.copyIcon
                )}
              </MessageActionButton>
            </div>
          ) : null}
        </div>
      ) : null}

      {renderAfter ? <div className="mb-2">{subComponent}</div> : null}
      {isLoading ? <span>{icons.activityIcon}</span> : null}
    </>
  );
}
