import { ChatRoutePage } from '@/components/copilot/chat-route-page';

export default async function ChatPage({
  params,
}: {
  params: Promise<{ chatId: string }>;
}) {
  const { chatId } = await params;

  return <ChatRoutePage chatId={chatId} mode="full" />;
}
