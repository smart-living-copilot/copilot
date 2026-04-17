import { CreateChatRedirectPage } from '@/components/copilot/chat-route-page';
import {
  type AppPageSearchParams,
  toSearchParamsString,
} from '@/lib/embed-chat-search-params';

export default async function EmbedChatPage({
  searchParams,
}: {
  searchParams: Promise<AppPageSearchParams>;
}) {
  const resolvedSearchParams = await searchParams;

  return (
    <CreateChatRedirectPage
      destinationBasePath="/embed/chat"
      queryString={toSearchParamsString(resolvedSearchParams)}
    />
  );
}
