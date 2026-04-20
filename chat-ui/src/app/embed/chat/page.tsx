import { EmbedChatPage as EmbedChatExperiencePage } from '@/components/copilot/chat-route-page';
import {
  areEmbedExamplesEnabledFromSearchParams,
  type AppPageSearchParams,
  toSearchParamsString,
} from '@/lib/embed-chat-search-params';

export default async function EmbedChatIndexPage({
  searchParams,
}: {
  searchParams: Promise<AppPageSearchParams>;
}) {
  const resolvedSearchParams = await searchParams;

  return (
    <EmbedChatExperiencePage
      embedQueryString={toSearchParamsString(resolvedSearchParams)}
      showEmbedExamplePrompts={areEmbedExamplesEnabledFromSearchParams(
        resolvedSearchParams,
      )}
    />
  );
}
