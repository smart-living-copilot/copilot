import { ChatRoutePage } from '@/components/wotbot/chat-route-page';

export default async function ChatPage({
  params,
}: {
  params: Promise<{ chatId: string }>;
}) {
  const { chatId } = await params;

  return <ChatRoutePage chatId={chatId} mode="full" />;
}
