import { EmbedChatPage as EmbedChatExperiencePage } from '@/components/copilot/chat-route-page';
import {
  getEmbedInitialPrefillFromSearchParams,
  getEmbedThemeFromSearchParams,
  type AppPageSearchParams,
  toSearchParamsString,
} from '@/lib/embed-chat-search-params';
import { getEmbedChatAllowedOrigins } from '@/lib/embed-chat-runtime-config';

export const dynamic = 'force-dynamic';

export default async function EmbedChatIndexPage({
  searchParams,
}: {
  searchParams: Promise<AppPageSearchParams>;
}) {
  const resolvedSearchParams = await searchParams;

  return (
    <EmbedChatExperiencePage
      allowedPrefillOrigins={getEmbedChatAllowedOrigins()}
      embedQueryString={toSearchParamsString(resolvedSearchParams)}
      initialPrefill={getEmbedInitialPrefillFromSearchParams(
        resolvedSearchParams,
      )}
      embedTheme={getEmbedThemeFromSearchParams(resolvedSearchParams)}
    />
  );
}
