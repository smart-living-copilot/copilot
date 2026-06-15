import {
  CopilotChat,
  CopilotChatInput,
  type CopilotChatInputProps,
  useCopilotKit,
} from '@copilotkit/react-core/v2';
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';

import { useDefaultExamplePrompts } from '@/components/copilot/chat-route/default-example-prompts';
import { MessageViewWithWotSummary } from '@/components/copilot/wot-interaction-summary';
import { WelcomeScreen } from '@/components/copilot/welcome-screen';
import {
  type EmbedChatPrefill,
  normalizeEmbedPrefillPrompt,
} from '@/lib/embed-chat';
import { useTheme, type Theme } from '@/components/theme-provider';

type EmbedChatPrefillRequest = EmbedChatPrefill & {
  id: number;
};

const PREFILL_DEDUPE_WINDOW_MS = 1000;

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
  agentReady,
  inputAppliedPrefillIdsRef,
  prefillRequest,
  submittedPrefillIdsRef,
  ...props
}: CopilotChatInputProps & {
  agentReady: boolean;
  inputAppliedPrefillIdsRef: { current: Set<number> };
  prefillRequest: EmbedChatPrefillRequest | null;
  submittedPrefillIdsRef: { current: Set<number> };
}) {
  const { isRunning, onChange, onSubmitMessage } = props;

  useEffect(() => {
    if (!prefillRequest) {
      return;
    }

    if (!inputAppliedPrefillIdsRef.current.has(prefillRequest.id)) {
      inputAppliedPrefillIdsRef.current.add(prefillRequest.id);
      onChange?.(prefillRequest.prompt);
    }

    if (
      prefillRequest.submit &&
      agentReady &&
      !submittedPrefillIdsRef.current.has(prefillRequest.id)
    ) {
      submittedPrefillIdsRef.current.add(prefillRequest.id);
      if (!isRunning) {
        onSubmitMessage?.(prefillRequest.prompt);
      }
    }
  }, [
    agentReady,
    inputAppliedPrefillIdsRef,
    isRunning,
    onChange,
    onSubmitMessage,
    prefillRequest,
    submittedPrefillIdsRef,
  ]);

  return <CopilotChatInput {...props} />;
}

function useAgentReady(agentId: string): boolean {
  const { copilotkit } = useCopilotKit();
  const [, forceUpdate] = useReducer((value: number) => value + 1, 0);

  useEffect(() => {
    const subscription = copilotkit.subscribe({
      onAgentsChanged: forceUpdate,
      onRuntimeConnectionStatusChanged: forceUpdate,
    });

    return () => subscription.unsubscribe();
  }, [copilotkit]);

  return Boolean(copilotkit.getAgent(agentId));
}

function EmbedThemeOverride({ theme }: { theme: Theme | null }) {
  const { setForcedTheme } = useTheme();

  useEffect(() => {
    setForcedTheme(theme);
    return () => setForcedTheme(null);
  }, [setForcedTheme, theme]);

  return null;
}

export function EmbedChatExperience({
  allowedPrefillOrigins,
  chatId,
  embedTheme,
  initialPrefill,
  showExamplePrompts,
}: {
  allowedPrefillOrigins: string[];
  chatId: string;
  embedTheme: Theme | null;
  initialPrefill: EmbedChatPrefill | null;
  showExamplePrompts: boolean;
}) {
  const agentReady = useAgentReady('copilot');
  const cleanupRequestedRef = useRef(false);
  const initialPrefillAppliedRef = useRef(false);
  const inputAppliedPrefillIdsRef = useRef<Set<number>>(new Set());
  const lastQueuedPrefillRef = useRef<{
    key: string;
    queuedAt: number;
  } | null>(null);
  const nextPrefillIdRef = useRef(0);
  const submittedPrefillIdsRef = useRef<Set<number>>(new Set());
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

    const key = `${prefill.submit ? 'submit' : 'prefill'}:${prompt}`;
    const now = Date.now();
    if (
      lastQueuedPrefillRef.current?.key === key &&
      now - lastQueuedPrefillRef.current.queuedAt < PREFILL_DEDUPE_WINDOW_MS
    ) {
      return;
    }

    lastQueuedPrefillRef.current = { key, queuedAt: now };
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
      return (
        <EmbedPrefillInput
          {...props}
          agentReady={agentReady}
          inputAppliedPrefillIdsRef={inputAppliedPrefillIdsRef}
          prefillRequest={prefillRequest}
          submittedPrefillIdsRef={submittedPrefillIdsRef}
        />
      );
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
  }, [agentReady, prefillRequest]);

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
      <EmbedThemeOverride theme={embedTheme} />
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
