import {
  CopilotChat,
  CopilotChatInput,
  type CopilotChatInputProps,
} from '@copilotkit/react-core/v2';
import type { Message } from '@copilotkit/shared';
import { MessageSquarePlus } from 'lucide-react';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
} from 'react';

import { AppSidebar } from '@/components/chat-sidebar';
import { blockSubmitWhileRunning } from '@/components/wotbot/chat-route/block-submit-while-running';
import { ChatAgentSync } from '@/components/wotbot/chat-route/chat-agent-sync';
import { getLatestTurnArtifacts } from '@/components/wotbot/chat-route/chat-message-utils';
import { PromptTextArea } from '@/components/wotbot/chat-route/prompt-text-area';
import { ReasoningEffortSelect } from '@/components/wotbot/chat-route/reasoning-effort-select';
import { LiveModePanel } from '@/components/wotbot/live-mode-panel';
import { MediaIngressControl } from '@/components/wotbot/media-ingress-control';
import { MessageViewWithWotSummary } from '@/components/wotbot/wot-interaction-summary';
import { WelcomeScreen } from '@/components/wotbot/welcome-screen';
import { SiteHeader } from '@/components/site-header';
import { Button } from '@/components/ui/button';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { useMediaIngressSession } from '@/hooks/use-media-ingress-session';
import { type ChatSummary } from '@/lib/chat-list-cache';
import type { ReasoningEffortConfig } from '@/lib/reasoning-effort';

export function FullChatExperience({
  chatId,
  handleNewChat,
  reasoningEffortConfig,
}: {
  chatId: string;
  handleNewChat: () => Promise<ChatSummary | null>;
  reasoningEffortConfig: ReasoningEffortConfig;
}) {
  const [loadedChatId, setLoadedChatId] = useState<string | null>(null);
  const [sidebarRefreshToken, setSidebarRefreshToken] = useState(0);
  const [historyRefreshToken, setHistoryRefreshToken] = useState(0);
  const [liveMessages, setLiveMessages] = useState<Message[]>([]);
  const wasLiveModeRef = useRef(false);
  const mediaSession = useMediaIngressSession(chatId);
  const handleSidebarRefresh = useCallback(() => {
    setSidebarRefreshToken((current) => current + 1);
  }, []);
  const historyLoaded = loadedChatId === chatId;

  const breadcrumbs = useMemo(() => [{ label: 'Chat', href: '/chat' }], []);
  const chatLabels = useMemo(
    () => ({ chatInputPlaceholder: 'Ask me anything...' }),
    [],
  );
  const renderWelcomeScreen = useCallback(
    (props: Record<string, unknown>) => (
      <WelcomeScreen {...props} historyLoaded={historyLoaded} />
    ),
    [historyLoaded],
  );
  const chatInput = useMemo(() => {
    function FullInput(props: CopilotChatInputProps) {
      // While the composer is empty and idle, the send button's slot shows
      // the voice/video call toggle instead (merged, ChatGPT-style); as soon
      // as there's a draft, or a response is in flight (so Stop stays
      // reachable), it swaps back to send/stop. Once a call connects,
      // showLiveMode below swaps out this whole composer, so there's no
      // "active call" state to reconcile with send here.
      const showSendButton = Boolean(props.value?.trim()) || props.isRunning;

      return (
        <CopilotChatInput {...props} textArea={PromptTextArea}>
          {({
            textArea,
            sendButton,
            disclaimer,
          }: {
            textArea: ReactElement;
            sendButton: ReactElement;
            disclaimer: ReactElement;
          }) => (
            <div className="mx-auto w-full max-w-3xl px-4 pb-4">
              <div className="rounded-lg border border-border bg-background px-3 py-2 shadow-sm">
                <div
                  className="min-h-16"
                  onKeyDownCapture={blockSubmitWhileRunning(props.isRunning)}
                >
                  {textArea}
                </div>
                <div className="flex items-center justify-end gap-2 border-t border-border pt-2">
                  <ReasoningEffortSelect config={reasoningEffortConfig} />
                  {showSendButton ? (
                    sendButton
                  ) : (
                    // Matches CopilotKit's own SendButton footprint exactly
                    // (a 36px `h-9 w-9` circle in a `mr-[10px]` wrapper) so
                    // swapping between the two doesn't shift the row.
                    <div className="mr-[10px]">
                      <MediaIngressControl
                        session={mediaSession}
                        size="icon-lg"
                      />
                    </div>
                  )}
                </div>
              </div>
              {disclaimer}
            </div>
          )}
        </CopilotChatInput>
      );
    }

    return Object.assign(FullInput, {
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
  }, [mediaSession, reasoningEffortConfig]);
  const showLiveMode = mediaSession.state !== 'idle';
  const liveArtifacts = useMemo(
    () => getLatestTurnArtifacts(liveMessages),
    [liveMessages],
  );

  useEffect(() => {
    if (!showLiveMode) {
      if (wasLiveModeRef.current) {
        const refreshFrame = window.requestAnimationFrame(() => {
          setHistoryRefreshToken((current) => current + 1);
        });
        wasLiveModeRef.current = false;
        return () => window.cancelAnimationFrame(refreshFrame);
      }
      wasLiveModeRef.current = false;
      return;
    }

    wasLiveModeRef.current = true;
    const interval = window.setInterval(() => {
      setHistoryRefreshToken((current) => current + 1);
    }, 2500);
    return () => window.clearInterval(interval);
  }, [showLiveMode]);

  return (
    <SidebarProvider className="relative h-dvh overflow-hidden text-foreground">
      <ChatAgentSync
        chatId={chatId}
        onHistoryLoaded={setLoadedChatId}
        onMessagesLoaded={setLiveMessages}
        onThreadUpdated={handleSidebarRefresh}
        refreshToken={historyRefreshToken}
      />

      <AppSidebar
        activeChatId={chatId}
        onNewChat={handleNewChat}
        refreshToken={sidebarRefreshToken}
      />

      <SidebarInset>
        <SiteHeader breadcrumbs={breadcrumbs}>
          <Button
            className="md:hidden"
            onClick={() => void handleNewChat()}
            size="sm"
            type="button"
            variant="outline"
          >
            <MessageSquarePlus className="size-4" />
            <span>New chat</span>
          </Button>
        </SiteHeader>

        <div className="flex min-h-0 flex-1 flex-col p-3 md:p-4">
          {showLiveMode ? (
            <LiveModePanel artifacts={liveArtifacts} session={mediaSession} />
          ) : (
            <CopilotChat
              agentId="wotbot"
              threadId={chatId}
              className="wotbot-chat flex-1"
              input={chatInput}
              labels={chatLabels}
              messageView={MessageViewWithWotSummary}
              welcomeScreen={renderWelcomeScreen}
            />
          )}
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
