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
  if (examplesFlag === null) {
    return true;
  }

  return !['0', 'false', 'no', 'off'].includes(examplesFlag.toLowerCase());
}
