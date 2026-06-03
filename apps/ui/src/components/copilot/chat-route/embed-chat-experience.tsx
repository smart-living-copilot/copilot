import { CopilotChat } from '@copilotkit/react-core/v2';
import { useCallback, useEffect, useMemo, useRef } from 'react';

import { useDefaultExamplePrompts } from '@/components/copilot/chat-route/default-example-prompts';
import { MessageViewWithWotSummary } from '@/components/copilot/wot-interaction-summary';
import { WelcomeScreen } from '@/components/copilot/welcome-screen';

export function EmbedChatExperience({
  chatId,
  showExamplePrompts,
}: {
  chatId: string;
  showExamplePrompts: boolean;
}) {
  const cleanupRequestedRef = useRef(false);
  const examplePrompts = useDefaultExamplePrompts();

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
          labels={chatLabels}
          messageView={MessageViewWithWotSummary}
          welcomeScreen={renderWelcomeScreen}
        />
      </div>
    </main>
  );
}
