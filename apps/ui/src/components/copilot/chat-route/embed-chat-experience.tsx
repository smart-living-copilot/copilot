import {
  CopilotChat,
  CopilotChatInput,
  type CopilotChatInputProps,
} from '@copilotkit/react-core/v2';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useDefaultExamplePrompts } from '@/components/copilot/chat-route/default-example-prompts';
import { MessageViewWithWotSummary } from '@/components/copilot/wot-interaction-summary';
import { WelcomeScreen } from '@/components/copilot/welcome-screen';
import {
  type EmbedChatPrefill,
  normalizeEmbedPrefillPrompt,
} from '@/lib/embed-chat';

type EmbedChatPrefillRequest = EmbedChatPrefill & {
  id: number;
};

function isDeckPrefillMessage(
  data: unknown,
): data is { prompt: unknown; submit?: unknown; type: 'deck:prefill' } {
  return (
    typeof data === 'object' &&
    data !== null &&
    'type' in data &&
    data.type === 'deck:prefill'
  );
}

function getDeckPrefill(data: unknown): EmbedChatPrefill | null {
  if (!isDeckPrefillMessage(data)) {
    return null;
  }

  const prompt = normalizeEmbedPrefillPrompt(data.prompt);
  if (!prompt) {
    return null;
  }

  return {
    prompt,
    submit: data.submit === true,
  };
}

function EmbedPrefillInput({
  prefillRequest,
  ...props
}: CopilotChatInputProps & {
  prefillRequest: EmbedChatPrefillRequest | null;
}) {
  const appliedPrefillIdsRef = useRef<Set<number>>(new Set());
  const { onChange, onSubmitMessage } = props;

  useEffect(() => {
    if (
      !prefillRequest ||
      appliedPrefillIdsRef.current.has(prefillRequest.id)
    ) {
      return;
    }

    appliedPrefillIdsRef.current.add(prefillRequest.id);
    onChange?.(prefillRequest.prompt);

    if (prefillRequest.submit) {
      onSubmitMessage?.(prefillRequest.prompt);
    }
  }, [onChange, onSubmitMessage, prefillRequest]);

  return <CopilotChatInput {...props} />;
}

export function EmbedChatExperience({
  allowedPrefillOrigins,
  chatId,
  initialPrefill,
  showExamplePrompts,
}: {
  allowedPrefillOrigins: string[];
  chatId: string;
  initialPrefill: EmbedChatPrefill | null;
  showExamplePrompts: boolean;
}) {
  const cleanupRequestedRef = useRef(false);
  const initialPrefillAppliedRef = useRef(false);
  const nextPrefillIdRef = useRef(0);
  const [prefillRequest, setPrefillRequest] =
    useState<EmbedChatPrefillRequest | null>(null);
  const examplePrompts = useDefaultExamplePrompts();
  const allowedPrefillOriginSet = useMemo(
    () => new Set(allowedPrefillOrigins),
    [allowedPrefillOrigins],
  );

  const isAllowedPrefillOrigin = useCallback(
    (origin: string) => {
      return (
        origin === window.location.origin || allowedPrefillOriginSet.has(origin)
      );
    },
    [allowedPrefillOriginSet],
  );

  const queuePrefill = useCallback((prefill: EmbedChatPrefill) => {
    const prompt = normalizeEmbedPrefillPrompt(prefill.prompt);
    if (!prompt) {
      return;
    }

    nextPrefillIdRef.current += 1;
    setPrefillRequest({
      id: nextPrefillIdRef.current,
      prompt,
      submit: prefill.submit,
    });
  }, []);

  const chatLabels = useMemo(
    () => ({
      title: 'Assistant',
      chatInputPlaceholder: 'Type your message...',
    }),
    [],
  );
  const renderWelcomeScreen = useCallback(
    (props: Record<string, unknown>) => (
      <WelcomeScreen
        {...props}
        examplePrompts={showExamplePrompts ? examplePrompts : []}
        historyLoaded
      />
    ),
    [examplePrompts, showExamplePrompts],
  );
  const chatInput = useMemo(() => {
    function EmbedInput(props: CopilotChatInputProps) {
      return <EmbedPrefillInput {...props} prefillRequest={prefillRequest} />;
    }

    return Object.assign(EmbedInput, {
      AddMenuButton: CopilotChatInput.AddMenuButton,
      AudioRecorder: CopilotChatInput.AudioRecorder,
      CancelTranscribeButton: CopilotChatInput.CancelTranscribeButton,
      Disclaimer: CopilotChatInput.Disclaimer,
      FinishTranscribeButton: CopilotChatInput.FinishTranscribeButton,
      SendButton: CopilotChatInput.SendButton,
      StartTranscribeButton: CopilotChatInput.StartTranscribeButton,
      TextArea: CopilotChatInput.TextArea,
      ToolbarButton: CopilotChatInput.ToolbarButton,
    });
  }, [prefillRequest]);

  useEffect(() => {
    if (!initialPrefill || initialPrefillAppliedRef.current) {
      return;
    }

    initialPrefillAppliedRef.current = true;
    queuePrefill(initialPrefill);
  }, [initialPrefill, queuePrefill]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (window.parent === window || event.source !== window.parent) {
        return;
      }

      if (!isAllowedPrefillOrigin(event.origin)) {
        return;
      }

      const prefill = getDeckPrefill(event.data);
      if (!prefill) {
        return;
      }

      queuePrefill(prefill);
    };

    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [isAllowedPrefillOrigin, queuePrefill]);

  useEffect(() => {
    const cleanupSession = () => {
      if (cleanupRequestedRef.current) {
        return;
      }

      cleanupRequestedRef.current = true;
      void fetch(`/api/chats/${encodeURIComponent(chatId)}`, {
        method: 'DELETE',
        keepalive: true,
      }).catch(() => {
        // Ephemeral embed cleanup is best-effort only.
      });
    };

    window.addEventListener('pagehide', cleanupSession);
    window.addEventListener('beforeunload', cleanupSession);

    return () => {
      window.removeEventListener('pagehide', cleanupSession);
      window.removeEventListener('beforeunload', cleanupSession);
    };
  }, [chatId]);

  return (
    <main className="embed-chat-shell flex h-dvh flex-col px-3 py-3 md:px-6 md:py-6">
      <div className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col">
        <CopilotChat
          agentId="copilot"
          threadId={chatId}
          className="smart-living-copilot-chat embed-chat-frame flex-1"
          input={chatInput}
          labels={chatLabels}
          messageView={MessageViewWithWotSummary}
          welcomeScreen={renderWelcomeScreen}
        />
      </div>
    </main>
  );
}
