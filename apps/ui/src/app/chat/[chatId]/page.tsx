import { ChatRoutePage } from '@/components/wotbot/chat-route-page';
import { getReasoningEffortRuntimeConfig } from '@/lib/reasoning-effort-runtime-config';

export const dynamic = 'force-dynamic';

export default async function ChatPage({
  params,
}: {
  params: Promise<{ chatId: string }>;
}) {
  const { chatId } = await params;

  return (
    <ChatRoutePage
      chatId={chatId}
      mode="full"
      reasoningEffortConfig={getReasoningEffortRuntimeConfig()}
    />
  );
}
