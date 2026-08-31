/**
 * Parses the credential interrupt a suspended run raises.
 *
 * The prompt that answers it lives in `interrupt-prompt.tsx`, in the transcript
 * rather than above it.
 */

export interface CredentialChallenge {
  kind: 'credential';
  status: 'credential_required' | 'credential_rejected';
  owner_kind: 'thing' | 'source';
  thing_id?: string;
  source_id?: string;
  security_name: string;
  scheme: string;
  message?: string;
}

export function parseCredentialChallenge(
  value: unknown,
): CredentialChallenge | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Record<string, unknown>;
  if (
    candidate.kind !== 'credential' ||
    !['credential_required', 'credential_rejected'].includes(
      String(candidate.status),
    ) ||
    typeof candidate.security_name !== 'string' ||
    typeof candidate.scheme !== 'string' ||
    !(
      typeof candidate.thing_id === 'string' ||
      (candidate.owner_kind === 'source' &&
        typeof candidate.source_id === 'string')
    )
  ) {
    return null;
  }
  return {
    kind: 'credential',
    status: candidate.status as CredentialChallenge['status'],
    owner_kind: candidate.owner_kind === 'source' ? 'source' : 'thing',
    ...(typeof candidate.thing_id === 'string'
      ? { thing_id: candidate.thing_id }
      : {}),
    ...(typeof candidate.source_id === 'string'
      ? { source_id: candidate.source_id }
      : {}),
    security_name: candidate.security_name,
    scheme: candidate.scheme,
    ...(typeof candidate.message === 'string'
      ? { message: candidate.message }
      : {}),
  };
}
