/**
 * Parses the source-registration interrupt a suspended run raises.
 *
 * The prompt that answers it lives in `interrupt-prompt.tsx`, in the transcript
 * rather than above it.
 */

import type { SourceDraft } from '@/lib/sources-api';

export interface SourceRegistrationInterrupt {
  kind: 'source_registration';
  draft: SourceDraft;
}

export function parseSourceRegistrationInterrupt(
  value: unknown,
): SourceRegistrationInterrupt | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Record<string, unknown>;
  if (
    candidate.kind !== 'source_registration' ||
    !candidate.draft ||
    typeof candidate.draft !== 'object' ||
    Array.isArray(candidate.draft)
  ) {
    return null;
  }
  const raw = candidate.draft as Record<string, unknown>;
  const draft: SourceDraft = {
    ...(typeof raw.url === 'string' ? { url: raw.url } : {}),
    ...(typeof raw.provider === 'string' ? { provider: raw.provider } : {}),
    ...(typeof raw.title === 'string' ? { title: raw.title } : {}),
    ...(typeof raw.description === 'string'
      ? { description: raw.description }
      : {}),
    ...(Array.isArray(raw.tags)
      ? {
          tags: raw.tags.filter(
            (item): item is string => typeof item === 'string',
          ),
        }
      : {}),
    ...(raw.config &&
    typeof raw.config === 'object' &&
    !Array.isArray(raw.config)
      ? { config: raw.config as Record<string, unknown> }
      : {}),
    ...(typeof raw.security_scheme === 'string'
      ? { security_scheme: raw.security_scheme }
      : {}),
  };
  if (!draft.url && !draft.provider) return null;
  return { kind: 'source_registration', draft };
}
