const SEMVER_PATTERN = /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/;

function normalizeAppVersion(value: string | undefined) {
  const trimmed = value?.trim();

  if (!trimmed) {
    return null;
  }

  if (SEMVER_PATTERN.test(trimmed)) {
    return `v${trimmed}`;
  }

  return trimmed;
}

export const APP_VERSION =
  normalizeAppVersion(process.env.NEXT_PUBLIC_APP_VERSION) ?? 'unknown';
