export interface ReasoningEffortOption {
  label: string;
  value: string;
}

export function parseReasoningEffortLevels(raw: string | undefined): string[] {
  if (!raw) {
    return [];
  }

  const seen = new Set<string>();
  for (const rawLevel of raw.split(',')) {
    const level = rawLevel.trim();
    if (level) {
      seen.add(level);
    }
  }
  return [...seen];
}

export function toReasoningEffortLabel(level: string): string {
  return level.length ? level[0].toUpperCase() + level.slice(1) : level;
}

export function resolveDefaultReasoningEffort(
  levels: string[],
  requested: string | undefined,
): string | null {
  if (levels.length === 0) {
    return null;
  }

  const trimmed = requested?.trim();
  if (trimmed && levels.includes(trimmed)) {
    return trimmed;
  }
  return levels[0];
}

export const REASONING_EFFORT_ENABLED =
  process.env.NEXT_PUBLIC_REASONING_EFFORT_ENABLED === 'true';

export const REASONING_EFFORT_LEVELS: string[] = parseReasoningEffortLevels(
  process.env.NEXT_PUBLIC_REASONING_EFFORT_LEVELS,
);

export const REASONING_EFFORT_OPTIONS: ReasoningEffortOption[] =
  REASONING_EFFORT_LEVELS.map((value) => ({
    value,
    label: toReasoningEffortLabel(value),
  }));

export const DEFAULT_REASONING_EFFORT: string | null =
  resolveDefaultReasoningEffort(
    REASONING_EFFORT_LEVELS,
    process.env.NEXT_PUBLIC_REASONING_EFFORT_DEFAULT,
  );

export function isReasoningEffortSelectorEnabled(): boolean {
  return REASONING_EFFORT_ENABLED && REASONING_EFFORT_LEVELS.length > 0;
}

// Remembers the last level a user picked across page loads (best-effort; a
// disabled/changed level list, or a browser that blocks storage, just falls
// back to DEFAULT_REASONING_EFFORT).
export const REASONING_EFFORT_STORAGE_KEY = 'wotbot-reasoning-effort';

export function resolveStoredReasoningEffort(
  levels: string[],
  stored: string | null,
  fallback: string | null,
): string | null {
  return stored && levels.includes(stored) ? stored : fallback;
}
