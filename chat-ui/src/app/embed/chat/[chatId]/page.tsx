import { ChatRoutePage } from '@/components/copilot/chat-route-page';
import {
  areEmbedExamplesEnabledFromSearchParams,
  type AppPageSearchParams,
  toSearchParamsString,
} from '@/lib/embed-chat-search-params';

export default async function EmbedChatThreadPage({
  params,
  searchParams,
}: {
  params: Promise<{ chatId: string }>;
  searchParams: Promise<AppPageSearchParams>;
}) {
  const { chatId } = await params;
  const resolvedSearchParams = await searchParams;

  return (
    <ChatRoutePage
      chatId={chatId}
      mode="embed"
      embedQueryString={toSearchParamsString(resolvedSearchParams)}
      showEmbedExamplePrompts={areEmbedExamplesEnabledFromSearchParams(
        resolvedSearchParams,
      )}
    />
  );
}
