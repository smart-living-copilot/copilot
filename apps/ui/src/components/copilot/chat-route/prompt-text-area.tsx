import { useCopilotChatConfiguration } from '@copilotkit/react-core/v2';
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  type TextareaHTMLAttributes,
} from 'react';

import { cn } from '@/lib/utils';

const MIN_PROMPT_ROWS = 2;
const MAX_PROMPT_ROWS = 5;

type PromptTextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

function getLineHeight(styles: CSSStyleDeclaration): number {
  const lineHeight = Number.parseFloat(styles.lineHeight);
  if (!Number.isNaN(lineHeight)) {
    return lineHeight;
  }

  const fontSize = Number.parseFloat(styles.fontSize);
  return Number.isNaN(fontSize) ? 24 : fontSize * 1.5;
}

function resizePromptTextArea(textarea: HTMLTextAreaElement) {
  const styles = window.getComputedStyle(textarea);
  const paddingTop = Number.parseFloat(styles.paddingTop) || 0;
  const paddingBottom = Number.parseFloat(styles.paddingBottom) || 0;
  const verticalPadding = paddingTop + paddingBottom;
  const lineHeight = getLineHeight(styles);
  const minHeight = Math.ceil(lineHeight * MIN_PROMPT_ROWS + verticalPadding);
  const maxHeight = Math.ceil(lineHeight * MAX_PROMPT_ROWS + verticalPadding);

  textarea.style.height = 'auto';
  textarea.style.minHeight = `${minHeight}px`;
  textarea.style.maxHeight = `${maxHeight}px`;

  const nextHeight = Math.min(
    Math.max(textarea.scrollHeight, minHeight),
    maxHeight,
  );
  textarea.style.height = `${nextHeight}px`;
  textarea.style.overflowY =
    textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
}

export const PromptTextArea = forwardRef<
  HTMLTextAreaElement,
  PromptTextAreaProps
>(function PromptTextArea(
  { autoFocus, className, onChange, placeholder, style, value, ...props },
  ref,
) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const labels = useCopilotChatConfiguration()?.labels;

  useImperativeHandle(ref, () => textareaRef.current as HTMLTextAreaElement);

  const resize = useCallback(() => {
    if (textareaRef.current) {
      resizePromptTextArea(textareaRef.current);
    }
  }, []);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    const handleFocus = () => {
      window.setTimeout(() => {
        textarea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 300);
    };

    textarea.addEventListener('focus', handleFocus);
    return () => textarea.removeEventListener('focus', handleFocus);
  }, []);

  useEffect(() => {
    if (autoFocus) {
      textareaRef.current?.focus();
    }
  }, [autoFocus]);

  useLayoutEffect(() => {
    resize();
  }, [resize, value]);

  return (
    <textarea
      {...props}
      ref={textareaRef}
      data-testid="copilot-chat-textarea"
      placeholder={placeholder ?? labels?.chatInputPlaceholder}
      rows={MIN_PROMPT_ROWS}
      value={value}
      onChange={onChange}
      className={cn(
        'resize-none bg-transparent text-[16px] leading-relaxed antialiased outline-none placeholder:text-[#00000077] dark:placeholder:text-[#fffc]',
        className,
      )}
      style={{ ...style, overflowY: 'hidden' }}
    />
  );
});
