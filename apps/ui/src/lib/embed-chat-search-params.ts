import {
  type EmbedChatPrefill,
  isEmbedAutosubmitValue,
  isEmbedDisabledValue,
  normalizeEmbedPrefillPrompt,
} from './embed-chat';
import type { Theme } from '@/components/theme-provider';

export type AppPageSearchParams = Record<string, string | string[] | undefined>;

function getFirstValue(value: string | string[] | undefined): string | null {
  if (typeof value === 'string') {
    return value;
  }

  if (Array.isArray(value)) {
    return value[0] ?? null;
  }

  return null;
}

export function toSearchParamsString(
  searchParams: AppPageSearchParams,
): string {
  const normalized = new URLSearchParams();

  for (const [key, value] of Object.entries(searchParams)) {
    if (typeof value === 'string') {
      normalized.set(key, value);
      continue;
    }

    if (!Array.isArray(value)) {
      continue;
    }

    for (const entry of value) {
      normalized.append(key, entry);
    }
  }

  return normalized.toString();
}

export function areEmbedExamplesEnabledFromSearchParams(
  searchParams: AppPageSearchParams,
): boolean {
  const examplesFlag = getFirstValue(searchParams.examples);
  return !isEmbedDisabledValue(examplesFlag);
}

export function areEmbedJobEventsEnabledFromSearchParams(
  searchParams: AppPageSearchParams,
): boolean {
  const jobEventsFlag = getFirstValue(searchParams.jobEvents);
  return !isEmbedDisabledValue(jobEventsFlag);
}

export function getEmbedThemeFromSearchParams(
  searchParams: AppPageSearchParams,
): Theme | null {
  const theme = getFirstValue(searchParams.theme)?.trim().toLowerCase();
  return theme === 'light' || theme === 'dark' || theme === 'system'
    ? theme
    : null;
}

export function getEmbedInitialPrefillFromSearchParams(
  searchParams: AppPageSearchParams,
): EmbedChatPrefill | null {
  const prompt = normalizeEmbedPrefillPrompt(
    getFirstValue(searchParams.prompt),
  );
  if (!prompt) {
    return null;
  }

  return {
    prompt,
    submit: isEmbedAutosubmitValue(getFirstValue(searchParams.autosubmit)),
  };
}
